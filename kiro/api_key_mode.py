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
API Key Mode support for Kiro Gateway.

When API_KEY_MODE=true, clients supply their own Kiro API key per-request
via the Authorization: Bearer <kiro_api_key> header.
Server-side credentials (REFRESH_TOKEN, KIRO_CREDS_FILE, KIRO_CLI_DB_FILE)
are not required in this mode.

The client's Bearer token is forwarded directly to the Kiro API.
"""

import asyncio
import uuid
from typing import Optional

import httpx
from fastapi import HTTPException, Request
from loguru import logger

from kiro.config import (
    BASE_RETRY_DELAY,
    FIRST_TOKEN_MAX_RETRIES,
    MAX_RETRIES,
    STREAMING_READ_TIMEOUT,
)
from kiro.utils import get_machine_fingerprint


def extract_bearer_token(auth_header: Optional[str]) -> Optional[str]:
    """
    Extract the token value from an Authorization: Bearer <token> header.

    Args:
        auth_header: Raw Authorization header value, or None.

    Returns:
        The token string, or None if the header is absent or not Bearer format.
    """
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def get_api_key_from_request(request: Request) -> str:
    """
    Extract the Kiro API key from the incoming request's Authorization header.

    In API_KEY_MODE the client's Bearer token IS the Kiro API key and is
    forwarded directly to the Kiro API without any server-side refresh.

    Args:
        request: FastAPI Request object.

    Returns:
        The Kiro API key string.

    Raises:
        HTTPException: 401 if the header is missing or not in Bearer format.
    """
    token = extract_bearer_token(request.headers.get("Authorization"))
    if not token:
        raise HTTPException(
            status_code=401,
            detail="API_KEY_MODE is enabled: supply your Kiro API key as 'Authorization: Bearer <key>'"
        )
    return token


def build_api_key_headers(token: str) -> dict:
    """
    Build Kiro API request headers using a caller-supplied token.

    Produces the same header set as kiro.utils.get_kiro_headers() but
    accepts the token directly instead of obtaining it from an auth manager.

    Args:
        token: Kiro access token supplied by the client.

    Returns:
        Dictionary of HTTP headers ready for use with httpx.
    """
    fingerprint = get_machine_fingerprint()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": (
            f"aws-sdk-js/1.0.27 ua/2.1 os/win32#10.0.19044 lang/js "
            f"md/nodejs#22.21.1 api/codewhispererstreaming#1.0.27 m/E "
            f"KiroIDE-0.7.45-{fingerprint}"
        ),
        "x-amz-user-agent": f"aws-sdk-js/1.0.27 KiroIDE-0.7.45-{fingerprint}",
        "x-amzn-codewhisperer-optout": "true",
        "x-amzn-kiro-agent-mode": "vibe",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=3",
    }


class ApiKeyModeClient:
    """
    Lightweight HTTP client for API_KEY_MODE.

    Sends requests to the Kiro API using a caller-supplied token.
    Handles 429 / 5xx retries with exponential back-off, but does NOT
    attempt token refresh on 403 (the caller owns the token).

    Supports both per-request clients and a shared application-level client.

    Args:
        token: Kiro API key supplied by the client.
        shared_client: Optional shared httpx.AsyncClient for connection pooling.
                       When provided it is used as-is and never closed by this class.
    """

    def __init__(self, token: str, shared_client: Optional[httpx.AsyncClient] = None):
        self.token = token
        self._shared_client = shared_client
        self._owns_client = shared_client is None
        self.client: Optional[httpx.AsyncClient] = shared_client

    async def _get_client(self, stream: bool = False) -> httpx.AsyncClient:
        if self._shared_client is not None:
            return self._shared_client
        if self.client is None or self.client.is_closed:
            if stream:
                timeout = httpx.Timeout(
                    connect=30.0,
                    read=STREAMING_READ_TIMEOUT,
                    write=30.0,
                    pool=30.0,
                )
            else:
                timeout = httpx.Timeout(timeout=300.0)
            self.client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
        return self.client

    async def close(self) -> None:
        """Close the client if this instance owns it."""
        if not self._owns_client:
            return
        if self.client and not self.client.is_closed:
            try:
                await self.client.aclose()
            except Exception as e:
                logger.warning(f"Error closing ApiKeyModeClient: {e}")

    async def request_with_retry(
        self,
        method: str,
        url: str,
        json_data: dict,
        stream: bool = False,
    ) -> httpx.Response:
        """
        Execute an HTTP request with retry logic.

        Retries on 429 and 5xx with exponential back-off.
        Returns 401 immediately on 403 (invalid user-supplied token).

        Args:
            method: HTTP method (e.g. "POST").
            url: Target URL.
            json_data: Request body as a dict (serialised to JSON).
            stream: Whether to use streaming mode.

        Returns:
            httpx.Response on success.

        Raises:
            HTTPException: On unrecoverable errors or after all retries exhausted.
        """
        max_retries = FIRST_TOKEN_MAX_RETRIES if stream else MAX_RETRIES
        client = await self._get_client(stream=stream)

        for attempt in range(max_retries):
            try:
                headers = build_api_key_headers(self.token)

                if stream:
                    headers["Connection"] = "close"
                    req = client.build_request(method, url, json=json_data, headers=headers)
                    logger.debug("ApiKeyModeClient: sending streaming request to Kiro API")
                    response = await client.send(req, stream=True)
                else:
                    logger.debug("ApiKeyModeClient: sending request to Kiro API")
                    response = await client.request(method, url, json=json_data, headers=headers)

                if response.status_code == 200:
                    return response

                if response.status_code == 403:
                    # User-supplied token is invalid — do not retry
                    logger.warning("ApiKeyModeClient: received 403, user-supplied Kiro API key is invalid")
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid Kiro API key (received 403 from Kiro API)"
                    )

                if response.status_code == 429:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"ApiKeyModeClient: 429 rate-limit, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue

                if 500 <= response.status_code < 600:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"ApiKeyModeClient: {response.status_code} server error, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue

                # Other status codes — return as-is for the caller to handle
                return response

            except HTTPException:
                raise  # propagate our own 401 immediately

            except httpx.TimeoutException as e:
                if attempt < max_retries - 1:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"ApiKeyModeClient: timeout, retrying in {delay}s (attempt {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"ApiKeyModeClient: timeout after {max_retries} attempts")
                    raise HTTPException(status_code=504, detail="Kiro API request timed out")

            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"ApiKeyModeClient: connection error, retrying in {delay}s (attempt {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"ApiKeyModeClient: connection error after {max_retries} attempts: {e}")
                    raise HTTPException(status_code=502, detail=f"Connection error: {e}")

        raise HTTPException(
            status_code=502,
            detail=f"Kiro API request failed after {max_retries} attempts"
        )

    async def __aenter__(self) -> "ApiKeyModeClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
