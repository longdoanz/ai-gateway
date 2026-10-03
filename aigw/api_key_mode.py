# -*- coding: utf-8 -*-

"""
Gateway Key support for AI Gateway.

Every request forwards straight to 9router (see aigw.nine_router_client and
aigw.routes_anthropic / aigw.routes_openai) — the legacy "API_KEY_MODE" that
let any caller-supplied bearer token through unchecked has been removed
(callers must now authenticate with PROXY_API_KEY, a Service Account key, or
a valid DB-registered Gateway Key). What remains here are the pieces still
genuinely in use:

- Extracting the caller's bearer token from a request.
- Resolving a Gateway Key (``iziaigw_`` prefix) to its DB id and recording
  its usage, for requests forwarded to 9router.
- ``get_usage_limits``/``build_api_key_headers``/``get_token_fingerprint``:
  used by aigw.usage.sync_worker's background credit-sync job, which still
  polls Kiro's getUsageLimits for any legacy Kiro API keys stored in the DB.
"""

from typing import Optional

import httpx
from fastapi import HTTPException, Request
from loguru import logger

from aigw.config import REGION, get_kiro_q_host
from aigw.usage.scheduler import is_db_configured


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
    Extract the bearer token from the incoming request's Authorization header.

    By the time this is called, ``verify_api_key``/``verify_anthropic_api_key``
    has already accepted the request (PROXY_API_KEY, a Service Account key, or
    a valid Gateway Key), so the header is guaranteed present; this just gets
    the raw value back out for Gateway Key usage-attribution.

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
            detail="Supply your API key as 'Authorization: Bearer <key>'"
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
    from aigw.db.repositories import hash_api_key
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

    Produces the same header set as aigw.utils.get_kiro_headers() but
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

    from aigw.config import (
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


async def _track_gateway_key_usage(gateway_key_id: int, input_tokens: int = 0, output_tokens: int = 0, model: str = "unknown", key_id: int | None = None, cache_read_tokens: int = 0, cache_creation_tokens: int = 0) -> None:
    if not is_db_configured():
        return
    try:
        from aigw.db.engine import async_session_factory
        from aigw.db.repositories import increment_gateway_key_usage
        from aigw.usage.daily_buffer import gateway_key_daily_buffer
        import time
        month = time.strftime("%Y-%m")
        async with async_session_factory() as session:
            await increment_gateway_key_usage(session, gateway_key_id, month, 1, key_id=key_id)
        today = time.strftime("%Y-%m-%d")
        gateway_key_daily_buffer.record(
            gateway_key_id, today, input_tokens, output_tokens, model=model, key_id=key_id,
            cache_read_tokens=cache_read_tokens, cache_creation_tokens=cache_creation_tokens,
        )
    except Exception as e:
        logger.debug(f"Gateway key usage tracking failed: {e}")


async def resolve_gateway_key_id(token: str | None) -> int | None:
    """Resolve an ``iziaigw_``-prefixed bearer token to its active Gateway Key id.

    Called from ``verify_api_key``/``verify_anthropic_api_key`` to decide
    whether a Gateway Key authenticates the request, and the resolved id is
    reused (via ``request.state.gateway_key_id``) to attribute 9router usage.
    Returns None when the token is missing, not a gateway key, the DB is
    unconfigured, the key is unknown/inactive, or on any error.
    """
    if not token or not token.startswith("iziaigw_") or not is_db_configured():
        return None
    try:
        from aigw.db.engine import async_session_factory
        from aigw.db.repositories import get_gateway_key_by_hash, hash_api_key
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

    async def _cb(
        input_tokens: int, output_tokens: int, model: str, cache_read_tokens: int = 0, cache_creation_tokens: int = 0
    ) -> None:
        # key_id=None: usage is attributed to the gateway key only, not a Kiro key.
        await _track_gateway_key_usage(
            gateway_key_id, input_tokens, output_tokens, model=model, key_id=None,
            cache_read_tokens=cache_read_tokens, cache_creation_tokens=cache_creation_tokens,
        )

    return _cb
