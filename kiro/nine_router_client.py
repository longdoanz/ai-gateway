# -*- coding: utf-8 -*-
"""
9Router fallback client.

Forwards OpenAI-compatible requests to a 9router instance when all Kiro
accounts are exhausted (402 quota / all accounts unavailable).

Usage:
    from kiro.nine_router_client import forward_to_nine_router, is_nine_router_enabled

    if is_nine_router_enabled():
        return await forward_to_nine_router(request, body_bytes)
"""

import asyncio
from typing import AsyncIterator, Optional

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from kiro.config import NINE_ROUTER_API_KEY, NINE_ROUTER_URL

# Headers that must not be forwarded upstream
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
    # httpx auto-decompresses response bodies; forwarding content-encoding
    # would make the client decode an already-decoded body.
    "content-encoding",
})


def is_nine_router_enabled() -> bool:
    """Return True when NINE_ROUTER_URL is configured."""
    return bool(NINE_ROUTER_URL)


def _build_headers(original_request: Request) -> dict[str, str]:
    """Build forwarding headers, replacing auth with 9router API key."""
    headers = {
        k: v
        for k, v in original_request.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }
    if NINE_ROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {NINE_ROUTER_API_KEY}"
    # Avoid compressed upstream bodies — httpx decompresses them and the
    # content-encoding header is stripped from the proxied response.
    headers["accept-encoding"] = "identity"
    return headers


async def forward_to_nine_router(
    original_request: Request,
    body: bytes,
    path: Optional[str] = None,
) -> StreamingResponse | JSONResponse:
    """
    Forward an OpenAI-compatible request to 9router and stream the response back.

    Args:
        original_request: The incoming FastAPI request (for headers and method).
        body: Raw request body bytes.
        path: Override path (default: same as original request path).

    Returns:
        StreamingResponse for streaming requests, JSONResponse for non-streaming.
    """
    if not NINE_ROUTER_URL:
        return JSONResponse(
            status_code=503,
            content={"error": {"message": "All Kiro accounts exhausted and 9router fallback is not configured.", "type": "service_unavailable"}},
        )

    target_path = path or original_request.url.path
    target_url = f"{NINE_ROUTER_URL.rstrip('/')}{target_path}"
    if original_request.url.query:
        target_url += f"?{original_request.url.query}"

    headers = _build_headers(original_request)
    logger.info(f"9router fallback: forwarding {original_request.method} {target_path}")

    # Open client manually (not as context manager) so the connection stays alive
    # while FastAPI streams the response back to the caller.
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0))
    try:
        response = await client.send(
            client.build_request(
                method=original_request.method,
                url=target_url,
                headers=headers,
                content=body,
            ),
            stream=True,
        )
    except httpx.ConnectError as exc:
        await client.aclose()
        logger.error(f"9router fallback: connection failed to {NINE_ROUTER_URL}: {exc}")
        return JSONResponse(
            status_code=503,
            content={"error": {"message": f"9router fallback unavailable: {exc}", "type": "service_unavailable"}},
        )
    except httpx.TimeoutException as exc:
        await client.aclose()
        logger.error(f"9router fallback: timeout: {exc}")
        return JSONResponse(
            status_code=504,
            content={"error": {"message": "9router fallback timed out.", "type": "timeout"}},
        )
    except Exception as exc:
        await client.aclose()
        logger.error(f"9router fallback: unexpected error: {exc}")
        return JSONResponse(
            status_code=502,
            content={"error": {"message": f"9router fallback error: {exc}", "type": "bad_gateway"}},
        )

    upstream_headers = {
        k: v for k, v in response.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }

    if response.status_code != 200:
        error_body = await response.aread()
        await response.aclose()
        await client.aclose()
        logger.warning(f"9router fallback returned {response.status_code}: {error_body[:200]}")
        return JSONResponse(
            status_code=response.status_code,
            content={"error": {"message": error_body.decode("utf-8", errors="replace"), "type": "nine_router_error"}},
        )

    async def _stream_and_close() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(
        _stream_and_close(),
        status_code=response.status_code,
        headers=upstream_headers,
        media_type=response.headers.get("content-type", "text/event-stream"),
    )
