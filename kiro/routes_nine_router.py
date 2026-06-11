# -*- coding: utf-8 -*-
"""
Reverse proxy route for 9router admin dashboard.

Mounts at /9router/{path} and forwards all requests to the internal 9router
service. Access is restricted to admin users via the ai-gateway JWT.

This lets admins reach the 9router dashboard through ai-gateway without
exposing 9router's port externally.
"""

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from loguru import logger

from kiro.config import NINE_ROUTER_API_KEY, NINE_ROUTER_URL
from kiro.dashboard.deps import require_admin
from kiro.db.models import User

router = APIRouter(tags=["nine-router-proxy"])

# Headers that must not be forwarded
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
    "authorization",  # replaced with 9router's own key
})


def _build_headers(request: Request) -> dict[str, str]:
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }
    if NINE_ROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {NINE_ROUTER_API_KEY}"
    # Tell 9router the real host for redirect generation
    headers["X-Forwarded-Host"] = request.headers.get("host", "localhost")
    headers["X-Forwarded-Prefix"] = "/9router"
    return headers


@router.api_route(
    "/9router/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def nine_router_proxy(
    path: str,
    request: Request,
    _admin: User = Depends(require_admin),
) -> Response:
    """
    Reverse proxy to 9router admin dashboard (admin-only).

    Strips the ai-gateway JWT and replaces it with the 9router API key.
    All HTTP methods are forwarded including streaming SSE responses.

    Args:
        path: Path suffix after /9router/
        request: Incoming FastAPI request.
        _admin: Injected admin user (enforces admin-only access).

    Returns:
        Proxied response from 9router.
    """
    if not NINE_ROUTER_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="9router is not configured (NINE_ROUTER_URL not set)",
        )

    target_url = f"{NINE_ROUTER_URL.rstrip('/')}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    headers = _build_headers(request)
    body = await request.body()

    logger.debug(f"9router proxy: {request.method} /{path} → {target_url}")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0),
            follow_redirects=False,
        ) as client:
            # Use streaming for all requests to handle SSE and large responses
            async with client.stream(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            ) as upstream:
                resp_headers = {
                    k: v
                    for k, v in upstream.headers.items()
                    if k.lower() not in _HOP_BY_HOP
                }

                # Rewrite redirect Location headers to stay within /9router/ prefix
                if "location" in resp_headers:
                    loc = resp_headers["location"]
                    nine_base = NINE_ROUTER_URL.rstrip("/")
                    if loc.startswith(nine_base):
                        resp_headers["location"] = "/9router" + loc[len(nine_base):]
                    elif loc.startswith("/") and not loc.startswith("/9router"):
                        resp_headers["location"] = "/9router" + loc

                content_type = upstream.headers.get("content-type", "")
                is_streaming = "text/event-stream" in content_type

                if is_streaming:
                    async def _stream():
                        async for chunk in upstream.aiter_bytes():
                            yield chunk

                    return StreamingResponse(
                        _stream(),
                        status_code=upstream.status_code,
                        headers=resp_headers,
                        media_type=content_type,
                    )
                else:
                    body_bytes = await upstream.aread()
                    return Response(
                        content=body_bytes,
                        status_code=upstream.status_code,
                        headers=resp_headers,
                        media_type=content_type or None,
                    )

    except httpx.ConnectError as exc:
        logger.error(f"9router proxy: connection failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot reach 9router at {NINE_ROUTER_URL}: {exc}",
        )
    except httpx.TimeoutException as exc:
        logger.error(f"9router proxy: timeout: {exc}")
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="9router request timed out")
    except Exception as exc:
        logger.error(f"9router proxy: unexpected error: {exc}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"9router proxy error: {exc}")
