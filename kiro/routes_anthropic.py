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
FastAPI routes for Anthropic Messages API.

Contains the /v1/messages endpoint compatible with Anthropic's Messages API.

Reference: https://docs.anthropic.com/en/api/messages
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Security, Header
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from loguru import logger

from kiro.config import PROXY_API_KEY, API_KEY_MODE
from kiro.models_anthropic import (
    AnthropicMessagesRequest,
    AnthropicCountTokensRequest,
)
from kiro.tokenizer import estimate_request_tokens
from kiro.nine_router_client import forward_to_nine_router


# --- Security scheme ---
# Anthropic uses x-api-key header instead of Authorization: Bearer
anthropic_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)
# Also support Authorization: Bearer for compatibility
auth_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_anthropic_api_key(
    x_api_key: Optional[str] = Security(anthropic_api_key_header),
    authorization: Optional[str] = Security(auth_header),
    request: Request = None,
) -> bool:
    """
    Verify API key for Anthropic API.

    In API_KEY_MODE the caller's token is the Kiro API key — we only check
    that at least one auth header is present, not that it matches PROXY_API_KEY.

    Also resolves the token as a Service Account key (``izisa_`` prefix) and
    stashes the result on ``request.state.service_account`` (None when the
    token is not a service-account key), independent of API_KEY_MODE, so
    request-path enforcement in the endpoints can read it. A resolved
    service account is accepted outright — it is a distinct token type from
    PROXY_API_KEY / Kiro API keys, so this does not change accept/reject
    behavior for any other token type. `request` defaults to None and is
    placed last / optional so this function stays callable exactly as
    before when invoked directly (e.g. in unit tests) without a real
    Request object; FastAPI itself always injects it via DI.

    Supports two authentication methods:
    1. x-api-key header (Anthropic native)
    2. Authorization: Bearer header (for compatibility)

    Args:
        x_api_key: Value from x-api-key header
        authorization: Value from Authorization header
        request: FastAPI Request, used to stash the resolved service-account
            context (if any) on request.state for the endpoint to read.

    Returns:
        True if key is valid

    Raises:
        HTTPException: 401 if key is invalid or missing
    """
    from kiro.db.repositories import SERVICE_ACCOUNT_KEY_PREFIX
    from kiro.service_accounts import resolve_service_account

    token = x_api_key or (
        authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    )
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
        raise HTTPException(
            status_code=401,
            detail={
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "Invalid or revoked service account key",
                },
            },
        )

    if API_KEY_MODE:
        if x_api_key or (authorization and authorization.startswith("Bearer ")):
            return True
        raise HTTPException(
            status_code=401,
            detail={
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "API_KEY_MODE is enabled: supply your Kiro API key via x-api-key or Authorization: Bearer",
                },
            },
        )

    # Check x-api-key first (Anthropic native)
    if x_api_key and x_api_key == PROXY_API_KEY:
        return True

    # Fall back to Authorization: Bearer
    if authorization and authorization == f"Bearer {PROXY_API_KEY}":
        return True

    logger.warning("Access attempt with invalid API key (Anthropic endpoint)")
    raise HTTPException(
        status_code=401,
        detail={
            "type": "error",
            "error": {
                "type": "authentication_error",
                "message": "Invalid or missing API key. Use x-api-key header or Authorization: Bearer."
            }
        }
    )


# --- Router ---
router = APIRouter(tags=["Anthropic API"])


@router.post("/v1/messages", dependencies=[Depends(verify_anthropic_api_key)])
async def messages(
    request: Request,
    request_data: AnthropicMessagesRequest,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version")
):
    """
    Anthropic Messages API endpoint.
    
    Compatible with Anthropic's /v1/messages endpoint.
    Accepts requests in Anthropic format and translates them to Kiro API.
    
    Required headers:
    - x-api-key: Your API key (or Authorization: Bearer)
    - anthropic-version: API version (optional, for compatibility)
    - Content-Type: application/json
    
    Args:
        request: FastAPI Request for accessing app.state
        request_data: Request in Anthropic MessagesRequest format
        anthropic_version: Anthropic API version header (optional)
    
    Returns:
        StreamingResponse for streaming mode (SSE)
        JSONResponse for non-streaming mode
    
    Raises:
        HTTPException: On validation or API errors
    """
    logger.info(f"Request to /v1/messages (model={request_data.model}, stream={request_data.stream})")

    if anthropic_version:
        logger.debug(f"Anthropic API version: {anthropic_version}")

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
                    "type": "error",
                    "error": {
                        "type": "permission_error",
                        "message": f"Model '{request_data.model}' is not permitted for this service account.",
                    },
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
    from kiro.api_key_mode import extract_bearer_token, _resolve_gateway_key_id_only, _make_nine_router_usage_cb
    # verify_anthropic_api_key already accepted this request via either
    # x-api-key (Anthropic native) or Authorization: Bearer — check both,
    # unlike the OpenAI endpoint which only ever sees Bearer tokens.
    raw_token = request.headers.get("x-api-key") or extract_bearer_token(request.headers.get("Authorization"))
    gateway_key_id = await _resolve_gateway_key_id_only(raw_token)
    return await forward_to_nine_router(
        request, await request.body(), on_usage=_make_nine_router_usage_cb(gateway_key_id)
    )


@router.post("/v1/messages/count_tokens", dependencies=[Depends(verify_anthropic_api_key)])
async def count_tokens_endpoint(
    request: Request,
    request_data: AnthropicCountTokensRequest,
):
    """
    Anthropic Count Tokens API endpoint.
    
    Returns estimated token count for the given request payload.
    Used by Claude Code to decide when to trigger conversation compaction.
    
    Uses the same fallback estimation as Anthropic streaming (message_start event),
    since Kiro API only provides accurate token counts after request completion.
    This endpoint is called BEFORE the actual request, so we cannot use Kiro's
    contextUsagePercentage (which is only available after generation completes).

    Service Account note: this endpoint is intentionally NOT gated by the
    allowlist. It never calls the Kiro pool or 9router and never consumes
    quota — it's a pure local token estimate over the request payload
    (see kiro.tokenizer.estimate_request_tokens) — so there is nothing for a
    service account to gain by probing it with a disallowed model, and
    blocking it would only break Claude Code's compaction check for
    otherwise-legitimate traffic.

    Args:
        request: FastAPI Request for accessing app.state
        request_data: Request in Anthropic MessagesRequest format
    
    Returns:
        JSONResponse with {"input_tokens": int}
    
    Raises:
        HTTPException: 401 if authentication fails (handled by dependency)
    """
    logger.info(f"Request to /v1/messages/count_tokens (model={request_data.model}, messages={len(request_data.messages)})")
    
    # Prepare data for tokenizer (same format as streaming message_start)
    messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
    tools_for_tokenizer = [tool.model_dump() for tool in request_data.tools] if request_data.tools else None
    
    # Handle system prompt (can be string or list of content blocks)
    if isinstance(request_data.system, list):
        system_for_tokenizer = [b.model_dump() if hasattr(b, "model_dump") else b for b in request_data.system]
    else:
        system_for_tokenizer = request_data.system
    
    # Use the SAME estimation logic as Anthropic streaming message_start
    request_token_stats = estimate_request_tokens(
        messages=messages_for_tokenizer,
        tools=tools_for_tokenizer,
        system_prompt=system_for_tokenizer,
        apply_claude_correction=True  # CRITICAL: Enable correction for Claude models
    )
    
    input_tokens = request_token_stats["total_tokens"]
    
    logger.info(f"Token count estimate: {input_tokens} tokens")
    
    return JSONResponse(content={"input_tokens": input_tokens})
