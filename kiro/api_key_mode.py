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
import json
import time
import uuid
from typing import Any, List, Optional

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from kiro.config import (
    BASE_RETRY_DELAY,
    FALLBACK_MODELS,
    FIRST_TOKEN_MAX_RETRIES,
    FORCE_AUTO_MODEL,
    MAX_RETRIES,
    MODEL_CACHE_TTL,
    REGION,
    STREAMING_READ_TIMEOUT,
    get_kiro_api_host,
    get_kiro_q_host,
)
from kiro.utils import get_machine_fingerprint


# Module-level cache for /v1/models in API_KEY_MODE: api_key -> (models_list, fetched_at)
_model_cache: dict = {}  # api_key -> (models_list, fetched_at)
_model_cache_lock = asyncio.Lock()


async def get_models_cached(api_key: str, app_state) -> List[dict]:
    """
    Lazily fetch available models from Kiro using the caller's API key.

    Caches results per api_key for MODEL_CACHE_TTL seconds. Falls back to
    FALLBACK_MODELS on any error.

    Args:
        api_key: Kiro API key supplied by the client.
        app_state: FastAPI app.state (unused, kept for interface symmetry).

    Returns:
        List of model dicts as returned by Kiro's ListAvailableModels endpoint.
    """
    global _model_cache

    now = time.time()
    cached = _model_cache.get(api_key)
    if cached is not None and now - cached[1] < MODEL_CACHE_TTL:
        return cached[0]

    async with _model_cache_lock:
        cached = _model_cache.get(api_key)
        if cached is not None and now - cached[1] < MODEL_CACHE_TTL:
            return cached[0]

        q_host = get_kiro_q_host(REGION)
        url = f"{q_host}/ListAvailableModels"
        headers = build_api_key_headers(api_key)
        params = {"origin": "AI_EDITOR"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=headers, params=params)
            if response.status_code == 200:
                models = response.json().get("models", [])
                _model_cache[api_key] = (models, now)
                return models
            raise Exception(f"HTTP {response.status_code}")
        except Exception as e:
            logger.warning(f"API_KEY_MODE: model fetch failed ({e}), using fallback")

    return FALLBACK_MODELS


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
        "tokentype": "API_KEY",
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


# ==================================================================================================
# ApiKeyAuthAdapter — duck-types KiroAuthManager for streaming functions
# ==================================================================================================

class ApiKeyAuthAdapter:
    """
    Minimal duck-type of KiroAuthManager for use in API_KEY_MODE.

    The streaming and MCP helper functions accept a KiroAuthManager but only
    use a small subset of its interface.  This adapter satisfies that interface
    using the caller-supplied token and the default region from config.

    Attributes:
        api_host: Kiro generateAssistantResponse host
        q_host: Kiro Q (MCP / ListAvailableModels) host
        profile_arn: Always None in API_KEY_MODE
        auth_type: Always KIRO_DESKTOP (no profileArn sent)
        fingerprint: Machine fingerprint for User-Agent
    """

    def __init__(self, token: str, region: str = REGION):
        self._token = token
        self._region = region
        self._fingerprint = get_machine_fingerprint()

        # Resolve hosts from config helpers
        self._api_host = get_kiro_api_host(region)
        self._q_host = get_kiro_q_host(region)

        self._auth_type = "api_key"

    async def get_access_token(self) -> str:
        """Return the caller-supplied token directly (no refresh)."""
        return self._token

    async def force_refresh(self) -> str:
        """No-op in API_KEY_MODE — token is owned by the caller."""
        return self._token

    @property
    def api_host(self) -> str:
        return self._api_host

    @property
    def q_host(self) -> str:
        return self._q_host

    @property
    def profile_arn(self) -> None:
        return None

    @property
    def auth_type(self):
        return self._auth_type

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def region(self) -> str:
        return self._region


# ==================================================================================================
# Chat handlers
# ==================================================================================================

async def handle_chat_openai(request: Request, request_data: Any) -> Any:
    # Note: truncation recovery and web_search auto-injection (from routes_openai.py)
    # are not applied in API_KEY_MODE. This is a known limitation.
    """
    Handle /v1/chat/completions in API_KEY_MODE.

    Extracts the Kiro API key from the Authorization header, builds the Kiro
    payload, and proxies the request using ApiKeyModeClient.

    Args:
        request: FastAPI Request (used to read the Authorization header and
                 access app.state.http_client / app.state.model_cache).
        request_data: Validated ChatCompletionRequest Pydantic model.

    Returns:
        StreamingResponse (stream=True) or JSONResponse (stream=False).
    """
    from kiro.converters_openai import build_kiro_payload
    from kiro.streaming_openai import (
        stream_with_first_token_retry,
        collect_stream_response,
    )
    from kiro.utils import generate_conversation_id
    from kiro.cache import ModelInfoCache

    token = get_api_key_from_request(request)
    auth_adapter = ApiKeyAuthAdapter(token)
    model_cache: ModelInfoCache = request.app.state.model_cache

    conversation_id = generate_conversation_id()

    if FORCE_AUTO_MODEL:
        request_data.model = "auto"

    try:
        kiro_payload = build_kiro_payload(request_data, conversation_id, "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    url = f"{auth_adapter.api_host}/generateAssistantResponse"
    logger.debug(f"[API_KEY_MODE] Kiro API URL: {url}")

    if request_data.stream:
        http_client = ApiKeyModeClient(token, shared_client=None)
    else:
        http_client = ApiKeyModeClient(token, shared_client=request.app.state.http_client)

    try:
        response = await http_client.request_with_retry("POST", url, kiro_payload, stream=True)

        if response.status_code != 200:
            try:
                error_content = await response.aread()
            except Exception:
                error_content = b"Unknown error"
            await http_client.close()
            error_text = error_content.decode("utf-8", errors="replace")
            try:
                error_json = json.loads(error_text)
                from kiro.kiro_errors import enhance_kiro_error
                error_info = enhance_kiro_error(error_json)
                error_text = error_info.user_message
            except (json.JSONDecodeError, KeyError):
                pass
            return JSONResponse(
                status_code=response.status_code,
                content={"error": {"message": error_text, "type": "kiro_api_error", "code": response.status_code}},
            )

        messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
        tools_for_tokenizer = [t.model_dump() for t in request_data.tools] if request_data.tools else None

        if request_data.stream:
            async def stream_wrapper():
                try:
                    async def make_retry_request():
                        return await http_client.request_with_retry("POST", url, kiro_payload, stream=True)

                    async for chunk in stream_with_first_token_retry(
                        make_request=make_retry_request,
                        client=http_client.client,
                        model=request_data.model,
                        model_cache=model_cache,
                        auth_manager=auth_adapter,
                        initial_response=response,
                        request_messages=messages_for_tokenizer,
                        request_tools=tools_for_tokenizer,
                    ):
                        yield chunk
                except GeneratorExit:
                    pass
                except Exception as e:
                    try:
                        yield "data: [DONE]\n\n"
                    except Exception:
                        pass
                    raise
                finally:
                    await http_client.close()

            return StreamingResponse(stream_wrapper(), media_type="text/event-stream")

        else:
            openai_response = await collect_stream_response(
                http_client.client,
                response,
                request_data.model,
                model_cache,
                auth_adapter,
                request_messages=messages_for_tokenizer,
                request_tools=tools_for_tokenizer,
            )
            await http_client.close()
            return JSONResponse(content=openai_response)

    except HTTPException:
        await http_client.close()
        raise
    except Exception as e:
        await http_client.close()
        logger.error(f"[API_KEY_MODE] Internal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


async def handle_chat_anthropic(request: Request, request_data: Any, anthropic_version: Optional[str] = None) -> Any:
    # Note: truncation recovery and web_search auto-injection (from routes_anthropic.py)
    # are not applied in API_KEY_MODE. This is a known limitation.
    """
    Handle /v1/messages in API_KEY_MODE.

    Extracts the Kiro API key from the Authorization or x-api-key header,
    builds the Kiro payload, and proxies the request using ApiKeyModeClient.

    Args:
        request: FastAPI Request.
        request_data: Validated AnthropicMessagesRequest Pydantic model.
        anthropic_version: Value of the anthropic-version header (optional).

    Returns:
        StreamingResponse (stream=True) or JSONResponse (stream=False).
    """
    from kiro.converters_anthropic import anthropic_to_kiro
    from kiro.streaming_anthropic import (
        stream_with_first_token_retry_anthropic,
        collect_anthropic_response,
    )
    from kiro.utils import generate_conversation_id
    from kiro.cache import ModelInfoCache

    # Support both Authorization: Bearer and x-api-key headers
    raw_token = (
        extract_bearer_token(request.headers.get("Authorization"))
        or request.headers.get("x-api-key")
    )
    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail={
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "API_KEY_MODE is enabled: supply your Kiro API key via Authorization: Bearer or x-api-key",
                },
            },
        )

    auth_adapter = ApiKeyAuthAdapter(raw_token)
    model_cache: ModelInfoCache = request.app.state.model_cache

    conversation_id = generate_conversation_id()

    if FORCE_AUTO_MODEL:
        request_data.model = "auto"

    try:
        kiro_payload = anthropic_to_kiro(request_data, conversation_id, "")
    except ValueError as e:
        logger.error(f"[API_KEY_MODE] Conversion error: {e}")
        return JSONResponse(
            status_code=400,
            content={"type": "error", "error": {"type": "invalid_request_error", "message": str(e)}},
        )

    url = f"{auth_adapter.api_host}/generateAssistantResponse"
    logger.debug(f"[API_KEY_MODE] Kiro API URL: {url}")

    if request_data.stream:
        http_client = ApiKeyModeClient(raw_token, shared_client=None)
    else:
        http_client = ApiKeyModeClient(raw_token, shared_client=request.app.state.http_client)

    messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
    tools_for_tokenizer = [t.model_dump() for t in request_data.tools] if request_data.tools else None
    if isinstance(request_data.system, list):
        system_for_tokenizer = [b.model_dump() if hasattr(b, "model_dump") else b for b in request_data.system]
    else:
        system_for_tokenizer = request_data.system

    try:
        response = await http_client.request_with_retry("POST", url, kiro_payload, stream=True)

        if response.status_code != 200:
            try:
                error_content = await response.aread()
            except Exception:
                error_content = b"Unknown error"
            await http_client.close()
            error_text = error_content.decode("utf-8", errors="replace")
            try:
                error_json = json.loads(error_text)
                from kiro.kiro_errors import enhance_kiro_error
                error_info = enhance_kiro_error(error_json)
                error_text = error_info.user_message
            except (json.JSONDecodeError, KeyError):
                pass
            return JSONResponse(
                status_code=response.status_code,
                content={"type": "error", "error": {"type": "api_error", "message": error_text}},
            )

        if request_data.stream:
            async def stream_wrapper():
                try:
                    async def make_retry_request():
                        return await http_client.request_with_retry("POST", url, kiro_payload, stream=True)

                    async for chunk in stream_with_first_token_retry_anthropic(
                        make_request=make_retry_request,
                        model=request_data.model,
                        model_cache=model_cache,
                        auth_manager=auth_adapter,
                        initial_response=response,
                        request_messages=messages_for_tokenizer,
                        request_tools=tools_for_tokenizer,
                        request_system=system_for_tokenizer,
                    ):
                        yield chunk
                except GeneratorExit:
                    pass
                except Exception as e:
                    try:
                        error_event = json.dumps({
                            "type": "error",
                            "error": {"type": "api_error", "message": str(e)},
                        })
                        yield f"event: error\ndata: {error_event}\n\n"
                    except Exception:
                        pass
                    raise
                finally:
                    await http_client.close()

            return StreamingResponse(stream_wrapper(), media_type="text/event-stream")

        else:
            anthropic_response = await collect_anthropic_response(
                response,
                request_data.model,
                model_cache,
                auth_adapter,
                request_messages=messages_for_tokenizer,
                request_tools=tools_for_tokenizer,
                request_system=system_for_tokenizer,
            )
            await http_client.close()
            return JSONResponse(content=anthropic_response)

    except HTTPException:
        await http_client.close()
        raise
    except Exception as e:
        await http_client.close()
        logger.error(f"[API_KEY_MODE] Internal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
