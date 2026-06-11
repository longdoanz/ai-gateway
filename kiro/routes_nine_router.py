# -*- coding: utf-8 -*-
"""
Reverse proxy route for 9router admin dashboard.

Mounts at /9router/{path} and forwards all requests to the internal 9router
service. Access is restricted to admin users via the ai-gateway JWT.

Auto-logs into 9router using NINE_ROUTER_PASSWORD and injects the session
cookie so admins reach the dashboard without a second login prompt.
"""

import asyncio
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from loguru import logger

from kiro.config import NINE_ROUTER_API_KEY, NINE_ROUTER_PASSWORD, NINE_ROUTER_URL
from kiro.dashboard.deps import require_admin
from kiro.db.models import User

router = APIRouter(tags=["nine-router-proxy"])

# Cached 9router session cookie (token + expiry timestamp)
_session_lock = asyncio.Lock()
_session_token: Optional[str] = None
_session_expires: float = 0.0
# Refresh 10 minutes before the 24h expiry
_SESSION_TTL = 23 * 3600

_HOP_BY_HOP = frozenset({
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
    "authorization",
})


async def _get_session_token(client: httpx.AsyncClient) -> Optional[str]:
    """Return a valid 9router auth_token, refreshing via auto-login if needed.

    Returns None when 9router runs in OIDC mode (no local password login) or is
    unreachable — the proxy then forwards the request without injecting a cookie
    and lets 9router's own auth (OIDC) handle access control.
    """
    global _session_token, _session_expires

    async with _session_lock:
        if _session_token and time.monotonic() < _session_expires:
            return _session_token

        if not NINE_ROUTER_PASSWORD:
            return None

        login_url = f"{NINE_ROUTER_URL.rstrip('/')}/api/auth/login"
        try:
            resp = await client.post(
                login_url,
                json={"password": NINE_ROUTER_PASSWORD},
                timeout=10.0,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # 9router may not support password login in OIDC mode — don't abort
            logger.warning(f"9router auto-login failed ({exc.response.status_code}): {exc.response.text}")
            return None
        except httpx.RequestError as exc:
            logger.warning(f"Cannot reach 9router for auto-login: {exc}")
            return None

        token = resp.cookies.get("auth_token")
        if not token:
            logger.warning("9router auto-login did not return auth_token cookie")
            return None

        _session_token = token
        _session_expires = time.monotonic() + _SESSION_TTL
        logger.info("9router: auto-login successful, session cached")
        return _session_token


def _build_headers(request: Request, session_token: Optional[str]) -> dict[str, str]:
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }
    if NINE_ROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {NINE_ROUTER_API_KEY}"
    headers["X-Forwarded-Host"] = request.headers.get("host", "localhost")
    headers["X-Forwarded-Prefix"] = "/9router"

    # Inject the 9router session cookie only when auto-login succeeded
    if session_token:
        existing = headers.get("cookie", "")
        cookies = {
            p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
            for p in existing.split(";")
            if "=" in p
        }
        cookies["auth_token"] = session_token
        headers["cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return headers


def _rewrite_location(loc: str) -> str:
    nine_base = NINE_ROUTER_URL.rstrip("/")
    if loc.startswith(nine_base):
        return "/9router" + loc[len(nine_base):]
    if loc.startswith("/") and not loc.startswith("/9router"):
        return "/9router" + loc
    return loc


@router.api_route(
    "/9router/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def nine_router_proxy(
    path: str,
    request: Request,
    _admin: User = Depends(require_admin),
) -> Response:
    if not NINE_ROUTER_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="9router is not configured (NINE_ROUTER_URL not set)",
        )

    target_url = f"{NINE_ROUTER_URL.rstrip('/')}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    body = await request.body()

    logger.debug(f"9router proxy: {request.method} /{path} → {target_url}")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0),
            follow_redirects=False,
        ) as client:
            for attempt in range(2):
                session_token = await _get_session_token(client)
                headers = _build_headers(request, session_token)

                async with client.stream(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                ) as upstream:
                    # If 9router rejects the injected session, invalidate and retry once
                    if upstream.status_code in (401, 403) and attempt == 0 and session_token and path != "api/auth/login":
                        global _session_token, _session_expires
                        _session_token = None
                        _session_expires = 0.0
                        logger.warning("9router: session rejected, invalidating cache and retrying")
                        await upstream.aread()
                        continue

                    # Use multi_items() — items() collapses duplicate keys via ", " join,
                    # which breaks Set-Cookie (each cookie must be its own header).
                    all_headers = list(upstream.headers.multi_items())
                    set_cookies = [v for k, v in all_headers if k.lower() == "set-cookie"]
                    resp_headers = {
                        k: v
                        for k, v in all_headers
                        if k.lower() not in _HOP_BY_HOP and k.lower() != "set-cookie"
                    }
                    if "location" in resp_headers:
                        resp_headers["location"] = _rewrite_location(resp_headers["location"])

                    content_type = upstream.headers.get("content-type", "")
                    is_streaming = "text/event-stream" in content_type

                    if is_streaming:
                        async def _stream():
                            async for chunk in upstream.aiter_bytes():
                                yield chunk

                        resp = StreamingResponse(
                            _stream(),
                            status_code=upstream.status_code,
                            headers=resp_headers,
                            media_type=content_type,
                        )
                    else:
                        body_bytes = await upstream.aread()
                        resp = Response(
                            content=body_bytes,
                            status_code=upstream.status_code,
                            headers=resp_headers,
                            media_type=content_type or None,
                        )

                    for cookie_val in set_cookies:
                        resp.headers.append("set-cookie", cookie_val)
                    return resp

    except httpx.ConnectError as exc:
        logger.error(f"9router proxy: connection failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot reach 9router at {NINE_ROUTER_URL}: {exc}",
        )
    except httpx.TimeoutException as exc:
        logger.error(f"9router proxy: timeout: {exc}")
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="9router request timed out")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"9router proxy: unexpected error: {exc}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"9router proxy error: {exc}")
