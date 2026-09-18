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
FastAPI routes for Kiro Gateway.

Contains all API endpoints:
- / and /health: Health check
- /v1/models: Models list
- /v1/chat/completions: Chat completions
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from loguru import logger

from kiro.config import (
    PROXY_API_KEY,
    APP_VERSION,
    API_KEY_MODE,
)
from kiro.models_openai import (
    OpenAIModel,
    ModelList,
    ChatCompletionRequest,
)
from kiro.nine_router_client import forward_to_nine_router


# --- Security scheme ---
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_key(auth_header: str = Security(api_key_header), request: Request = None) -> bool:
    """
    Verify API key in Authorization header.

    In API_KEY_MODE the Bearer token is the caller's Kiro API key — we only
    check that it is present, not that it matches PROXY_API_KEY.

    Also resolves the token as a Service Account key (``izisa_`` prefix) and
    stashes the result on ``request.state.service_account`` (None when the
    token is not a service-account key), independent of API_KEY_MODE, so
    request-path enforcement in the endpoints can read it. A resolved
    service account is accepted outright — it is a distinct token type from
    PROXY_API_KEY / Kiro API keys, so this does not change accept/reject
    behavior for any other token type. `request` defaults to None (rather
    than being a required first positional param) so this function stays
    callable exactly as before when invoked directly (e.g. in unit tests)
    without a real Request object; FastAPI itself always injects it via DI.

    Expects format: "Bearer {PROXY_API_KEY}" (or any Bearer token in API_KEY_MODE)

    Args:
        auth_header: Authorization header value
        request: FastAPI Request, used to stash the resolved service-account
            context (if any) on request.state for the endpoint to read.

    Returns:
        True if key is valid

    Raises:
        HTTPException: 401 if key is invalid or missing
    """
    from kiro.db.repositories import SERVICE_ACCOUNT_KEY_PREFIX
    from kiro.service_accounts import resolve_service_account

    token = auth_header[7:] if auth_header and auth_header.startswith("Bearer ") else None
    service_account = await resolve_service_account(token) if token else None
    if request is not None:
        request.state.service_account = service_account
    if service_account is not None:
        return True

    # A token carrying our own prefix that did NOT resolve is revoked, disabled,
    # or forged — reject it here. Without this it would fall through to the
    # API_KEY_MODE branch below, which accepts any bearer token, so revoking a
    # key or deactivating an account would have no effect whatsoever.
    if token and token.startswith(SERVICE_ACCOUNT_KEY_PREFIX):
        logger.warning("Rejected a service-account key that is revoked, disabled, or unknown.")
        raise HTTPException(status_code=401, detail="Invalid or revoked service account key")

    if API_KEY_MODE:
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="API_KEY_MODE is enabled: supply your Kiro API key as 'Authorization: Bearer <key>'"
            )
        return True
    if not auth_header or auth_header != f"Bearer {PROXY_API_KEY}":
        logger.warning("Access attempt with invalid API key.")
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return True


# --- Router ---
router = APIRouter()


@router.get("/")
async def root():
    """
    Health check endpoint.
    
    Returns:
        Status and application version
    """
    return {
        "status": "ok",
        "message": "Kiro Gateway is running",
        "version": APP_VERSION
    }


@router.get("/health")
async def health():
    """
    Detailed health check.
    
    Returns:
        Status, timestamp and version
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": APP_VERSION
    }

@router.get("/v1/models", response_model=ModelList, dependencies=[Depends(verify_api_key)])
async def get_models(request: Request):
    """
    Return list of available models.

    Sourced live from 9router's own /v1/models (short in-process TTL cache,
    see fetch_nine_router_models) — the sole upstream, so this always
    reflects what 9router can actually route to.

    Args:
        request: FastAPI Request for accessing app.state

    Returns:
        ModelList with available models in consistent format (with dots)
    """
    logger.info("Request to /v1/models")

    service_account = getattr(request.state, "service_account", None)
    if service_account is not None:
        # A Service Account is not a Kiro/Gateway API key — return exactly its
        # admin-configured allowlist so it's the first call a client makes
        # (e.g. Claude Code probing /v1/models) discovers what it can use.
        models = [
            OpenAIModel(id=mid, object="model", created=0, owned_by="anthropic")
            for mid in service_account.allowed_models
        ]
        return ModelList(object="list", data=models)

    from kiro.nine_router_client import fetch_nine_router_models
    model_ids = await fetch_nine_router_models()
    models = [OpenAIModel(id=mid, object="model", created=0, owned_by="anthropic") for mid in model_ids]
    return ModelList(object="list", data=models)


@router.get("/v1/usage", dependencies=[Depends(verify_api_key)])
async def get_usage(request: Request, resource_type: str = "AGENTIC_REQUEST"):
    """
    Proxy to Kiro getUsageLimits API. Only available in API_KEY_MODE.
    """
    if not API_KEY_MODE:
        raise HTTPException(status_code=501, detail="Usage endpoint is only available in API_KEY_MODE")

    # A service-account key is not a Kiro credential. Without this guard it
    # would be forwarded verbatim to Kiro's getUsageLimits, leaking our own
    # secret to a third party for a request that can only ever fail.
    if getattr(request.state, "service_account", None) is not None:
        raise HTTPException(
            status_code=404,
            detail="Kiro usage limits do not apply to service accounts; see the Service Accounts dashboard.",
        )

    # The legacy Kiro-account usage-limit concept this endpoint proxied
    # doesn't apply to direct-forwarded gateway keys — there's no Kiro
    # account behind them to query for a usage limit.
    raise HTTPException(status_code=501, detail="Usage endpoint is not available for direct-forwarded gateway keys")


@router.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request, request_data: ChatCompletionRequest):
    """
    Chat completions endpoint - compatible with OpenAI API.
    
    Accepts requests in OpenAI format and translates them to Kiro API.
    Supports streaming and non-streaming modes.
    
    Args:
        request: FastAPI Request for accessing app.state
        request_data: Request in OpenAI ChatCompletionRequest format
    
    Returns:
        StreamingResponse for streaming mode
        JSONResponse for non-streaming mode
    
    Raises:
        HTTPException: On validation or API errors
    """
    logger.info(f"Request to /v1/chat/completions (model={request_data.model}, stream={request_data.stream})")

    # Service Account enforcement — MUST run before the unconditional 9router
    # forward below. Service accounts always forward straight to 9router with
    # the admin-configured override disabled, so the model validated here is
    # the model that actually goes upstream.
    service_account = getattr(request.state, "service_account", None)
    if service_account is not None:
        from kiro.service_accounts import is_model_allowed, make_service_account_usage_cb

        if not is_model_allowed(request_data.model, service_account.allowed_models):
            logger.warning(
                f"Service account '{service_account.name}' requested disallowed model '{request_data.model}'"
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "message": f"Model '{request_data.model}' is not permitted for this service account.",
                        "type": "permission_error",
                        "code": 403,
                    }
                },
            )
        return await forward_to_nine_router(
            request,
            await request.body(),
            on_usage=make_service_account_usage_cb(service_account.id),
            apply_override=False,
        )

    # Every request forwards straight to 9router — the sole upstream now that
    # the legacy Kiro account/key pool has been fully retired.
    from kiro.api_key_mode import get_api_key_from_request, _resolve_gateway_key_id_only, _make_nine_router_usage_cb
    raw_token = get_api_key_from_request(request)
    gateway_key_id = await _resolve_gateway_key_id_only(raw_token)
    return await forward_to_nine_router(
        request, await request.body(), on_usage=_make_nine_router_usage_cb(gateway_key_id)
    )
