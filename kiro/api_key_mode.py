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

Every request now forwards straight to 9router (see kiro.nine_router_client
and kiro.routes_anthropic / kiro.routes_openai) — the legacy Kiro account/key
pool request-handling path that used to live in this module has been
removed. What remains here are the pieces still genuinely in use:

- Extracting the caller's bearer token (Gateway Keys / Kiro keys) from a
  request.
- Resolving a Gateway Key (``iziaigw_`` prefix) to its DB id and recording
  its usage, for requests forwarded to 9router.
- ``get_usage_limits``/``build_api_key_headers``/``get_token_fingerprint``:
  used by kiro.usage.sync_worker's background credit-sync job, which still
  polls Kiro's getUsageLimits for any legacy Kiro API keys stored in the DB.
"""

from typing import Optional

import httpx
from fastapi import HTTPException, Request
from loguru import logger

from kiro.config import REGION, get_kiro_q_host
from kiro.usage.scheduler import is_db_configured


async def get_usage_limits(api_key: str, resource_type: str = "AGENTIC_REQUEST") -> dict:
    """
    Fetch usage limits from Kiro API using the caller's API key.

    Args:
        api_key: Kiro API key supplied by the client.
        resource_type: Resource type to query (default: AGENTIC_REQUEST).

    Returns:
        Raw JSON response from Kiro's getUsageLimits endpoint.

    Raises:
        HTTPException: On auth failure or unexpected errors.
    """
    q_host = get_kiro_q_host(REGION)
    url = f"{q_host}/getUsageLimits"
    headers = build_api_key_headers(api_key, stream=False)
    params = {"origin": "AI_EDITOR", "resourceType": resource_type}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)

        if response.status_code == 200:
            return response.json()

        if response.status_code == 403:
            raise HTTPException(
                status_code=401,
                detail="Invalid Kiro API key (received 403 from Kiro API)",
            )

        raise HTTPException(
            status_code=response.status_code,
            detail=f"Kiro API returned {response.status_code}: {response.text[:500]}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API_KEY_MODE: getUsageLimits failed: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch usage limits: {e}")


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

    The client's Bearer token IS the Kiro/Gateway API key and is forwarded
    directly (to 9router, or to Kiro for the sync-worker's usage-limit
    lookups) without any server-side refresh.

    Args:
        request: FastAPI Request object.

    Returns:
        The API key string.

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


def get_token_fingerprint(token: str) -> str:
    """
    Generates a unique fingerprint from a Kiro API token.

    In API Key Mode, each user has their own token, so we derive
    a unique fingerprint per token. This makes each user look like
    a separate Kiro IDE installation to AWS, which is more natural
    than all users sharing the same server-level fingerprint.

    Args:
        token: Kiro API key supplied by the client.

    Returns:
        SHA256 hex digest of the token (64 chars).
    """
    from kiro.db.repositories import hash_api_key
    return hash_api_key(token)


def build_api_key_headers(
    token: str,
    stream: bool = False,
    attempt: int = 1,
    max_attempts: Optional[int] = None,
    invocation_id: Optional[str] = None,
) -> dict:
    """
    Build Kiro API request headers using a caller-supplied token.

    Produces the same header set as kiro.utils.get_kiro_headers() but
    accepts the token directly instead of obtaining it from an auth manager.
    Uses a per-token fingerprint so each API key looks like a separate
    Kiro IDE installation.

    Args:
        token: Kiro access token supplied by the client.
        stream: If True, use streaming endpoint headers (generateAssistantResponse).
        attempt: Current attempt number (1-based). Used in amz-sdk-request header.
        max_attempts: Max attempts for this invocation. Defaults to 3 (stream) or 1 (non-stream).
        invocation_id: Stable UUID for amz-sdk-invocation-id. Generated fresh if not provided.

    Returns:
        Dictionary of HTTP headers ready for use with httpx.
    """
    import uuid

    from kiro.config import (
        KIRO_IDE_VERSION, KIRO_SDK_VERSION, KIRO_OS_STRING,
        KIRO_NODEJS_VERSION, KIRO_API_MODULE, KIRO_API_MODULE_VERSION,
        KIRO_M_FLAGS,
        KIRO_STREAMING_SDK_VERSION, KIRO_STREAMING_API_MODULE,
        KIRO_STREAMING_API_MODULE_VERSION, KIRO_STREAMING_M_FLAGS,
    )
    fingerprint = get_token_fingerprint(token)

    if stream:
        sdk_ver = KIRO_STREAMING_SDK_VERSION
        api_mod = KIRO_STREAMING_API_MODULE
        api_mod_ver = KIRO_STREAMING_API_MODULE_VERSION
        m_flags = KIRO_STREAMING_M_FLAGS
        default_max = 3
    else:
        sdk_ver = KIRO_SDK_VERSION
        api_mod = KIRO_API_MODULE
        api_mod_ver = KIRO_API_MODULE_VERSION
        m_flags = KIRO_M_FLAGS
        default_max = 1

    effective_max = max_attempts if max_attempts is not None else default_max
    effective_invocation_id = invocation_id if invocation_id is not None else str(uuid.uuid4())

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": (
            f"aws-sdk-js/{sdk_ver} ua/2.1 os/{KIRO_OS_STRING} "
            f"lang/js md/nodejs#{KIRO_NODEJS_VERSION} "
            f"api/{api_mod}#{api_mod_ver} "
            f"m/{m_flags} KiroIDE-{KIRO_IDE_VERSION}-{fingerprint}"
        ),
        "x-amz-user-agent": f"aws-sdk-js/{sdk_ver} KiroIDE-{KIRO_IDE_VERSION}-{fingerprint}",
        "x-amzn-codewhisperer-optout": "true",
        "x-amzn-kiro-agent-mode": "vibe",
        "amz-sdk-invocation-id": effective_invocation_id,
        "amz-sdk-request": f"attempt={attempt}; max={effective_max}",
        "Connection": "close",
        "tokentype": "API_KEY",
    }


async def _track_gateway_key_usage(gateway_key_id: int, input_tokens: int = 0, output_tokens: int = 0, model: str = "unknown", key_id: int | None = None) -> None:
    if not is_db_configured():
        return
    try:
        from kiro.db.engine import async_session_factory
        from kiro.db.repositories import get_canonical_usage_key_id, increment_gateway_key_usage
        from kiro.usage.daily_buffer import gateway_key_daily_buffer
        import time
        month = time.strftime("%Y-%m")
        async with async_session_factory() as session:
            canonical_key_id = key_id
            if key_id is not None:
                canonical_key_id = await get_canonical_usage_key_id(session, key_id)
            await increment_gateway_key_usage(session, gateway_key_id, month, 1, key_id=canonical_key_id)
        today = time.strftime("%Y-%m-%d")
        gateway_key_daily_buffer.record(gateway_key_id, today, input_tokens, output_tokens, model=model, key_id=canonical_key_id)
    except Exception as e:
        logger.debug(f"Gateway key usage tracking failed: {e}")


async def _resolve_gateway_key_id_only(token: str) -> int | None:
    """Look up just the gateway_key_id for an iziaigw_ token, without resolving a Kiro key.

    Used by the 503 fallback path (pool empty) so 9router usage can still be
    attributed to the gateway key. Returns None when not a gateway key, DB is
    unconfigured, the key is unknown/inactive, or on any error.
    """
    if not token.startswith("iziaigw_") or not is_db_configured():
        return None
    try:
        from kiro.db.engine import async_session_factory
        from kiro.db.repositories import get_gateway_key_by_hash, hash_api_key
        key_hash = hash_api_key(token)
        async with async_session_factory() as session:
            gk = await get_gateway_key_by_hash(session, key_hash)
        if gk is None or not gk.is_active:
            return None
        return gk.id
    except Exception as e:
        logger.debug(f"Gateway key id resolution failed: {e}")
        return None


def _make_nine_router_usage_cb(gateway_key_id: int | None):
    """
    Build an on_usage callback for the 9router proxy fallback.

    When a request falls back to 9router the Kiro key pool served nothing, so we
    do NOT touch per-Kiro-key usage. We only record gateway-key usage (request
    count + daily tokens) so the gateway-key dashboard still reflects the traffic.
    Returns None when there is nothing to track (no gateway key / no DB).
    """
    if gateway_key_id is None or not is_db_configured():
        return None

    async def _cb(input_tokens: int, output_tokens: int, model: str) -> None:
        # key_id=None: usage is attributed to the gateway key only, not a Kiro key.
        await _track_gateway_key_usage(
            gateway_key_id, input_tokens, output_tokens, model=model, key_id=None
        )

    return _cb
