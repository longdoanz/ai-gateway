# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Debug logging middleware for Kiro Gateway.

This middleware initializes debug logging BEFORE Pydantic validation,
which allows capturing validation errors (422) in debug logs.

The middleware:
1. Intercepts requests to API endpoints (/v1/chat/completions, /v1/messages)
2. Calls prepare_new_request() to initialize buffers and loguru sink
3. Reads and logs the raw request body
4. Passes the request to the next handler

Flush/discard operations are handled by:
- Route handlers (for successful requests and Kiro API errors)
- Exception handlers (for validation errors and other exceptions)
"""

from starlette.types import ASGIApp, Receive, Scope, Send
from loguru import logger

from kiro.config import DEBUG_MODE


# API endpoints that should have debug logging enabled
# These are the main API endpoints that process user requests
LOGGED_ENDPOINTS = frozenset({
    "/v1/chat/completions",  # OpenAI-compatible endpoint
    "/v1/messages",          # Anthropic-compatible endpoint
})


class DebugLoggerMiddleware:
    """
    Pure ASGI middleware for initializing debug logging on API requests.

    Uses pure ASGI (not BaseHTTPMiddleware) to avoid anyio cancel-scope
    interference with SQLAlchemy/asyncpg connection cleanup.

    Lifecycle:
    - prepare_new_request(): Called here (before validation)
    - log_request_body(): Called here (raw body from client)
    - log_kiro_request_body(): Called in route handlers (transformed payload)
    - flush_on_error() / discard_buffers(): Called in routes or exception handlers
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path not in LOGGED_ENDPOINTS or DEBUG_MODE == "off":
            await self.app(scope, receive, send)
            return

        try:
            from kiro.debug_logger import debug_logger
        except ImportError:
            logger.warning("debug_logger not available, skipping debug logging")
            await self.app(scope, receive, send)
            return

        debug_logger.prepare_new_request()

        # Drain the body from the ASGI receive channel so we can log it,
        # then replay it for downstream handlers.
        body_chunks: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            body_chunks.append(message.get("body", b""))
            more_body = message.get("more_body", False)

        body = b"".join(body_chunks)

        if body:
            try:
                debug_logger.log_request_body(body)
            except Exception as e:
                logger.warning(f"Failed to log request body for debug logging: {e}")

        # Replay the body once, then fall back to the real receive for
        # subsequent messages (e.g. http.disconnect).
        replayed = False

        async def replay_receive() -> dict:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)
