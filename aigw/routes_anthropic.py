# -*- coding: utf-8 -*-

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

from aigw.config import PROXY_API_KEY
from aigw.models_anthropic import (
    AnthropicMessagesRequest,
    AnthropicCountTokensRequest,
)
from aigw.tokenizer import estimate_request_tokens
from aigw.nine_router_client import forward_to_nine_router


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

    Also resolves the token as a Service Account key (``izisa_`` prefix) and
    stashes the result on ``request.state.service_account`` (None when the
    token is not a service-account key), so request-path enforcement in the
    endpoints can read it. A resolved service account is accepted outright —
    it is a distinct token type from PROXY_API_KEY / Gateway Keys, so this
    does not change accept/reject behavior for any other token type.

    Also resolves the token as a Gateway Key (``iziaigw_`` prefix,
    DB-registered via the dashboard) and stashes the resolved id on
    ``request.state.gateway_key_id`` (None when not a gateway key) so the
    endpoint can attribute 9router usage without a second DB lookup. A
    resolved Gateway Key is accepted outright, same as a Service Account.

    `request` defaults to None and is placed last / optional so this function
    stays callable exactly as before when invoked directly (e.g. in unit
    tests) without a real Request object; FastAPI itself always injects it
    via DI.

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
    from aigw.api_key_mode import resolve_gateway_key_id
    from aigw.db.repositories import GATEWAY_KEY_PREFIX, SERVICE_ACCOUNT_KEY_PREFIX
    from aigw.service_accounts import resolve_service_account

    token = x_api_key or (
        authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    )
    service_account = await resolve_service_account(token) if token else None
    if request is not None:
        request.state.service_account = service_account
    if service_account is not None:
        return True

    # A token carrying our own prefix that did NOT resolve is revoked, disabled,
    # or forged — reject it here rather than falling through to the generic
    # "invalid API key" check below, so the error is unambiguous.
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

    gateway_key_id = await resolve_gateway_key_id(token)
    if request is not None:
        request.state.gateway_key_id = gateway_key_id
    if gateway_key_id is not None:
        return True

    # Same reasoning as the service-account check above: a forged/revoked
    # Gateway Key must not silently fall through to any other acceptance path.
    if token and token.startswith(GATEWAY_KEY_PREFIX):
        logger.warning("Rejected a gateway key that is revoked, disabled, or unknown.")
        raise HTTPException(
            status_code=401,
            detail={
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "Invalid or revoked gateway key",
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
        from aigw.service_accounts import is_model_allowed, make_service_account_usage_cb

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
    from aigw.api_key_mode import _make_nine_router_usage_cb
    # verify_anthropic_api_key already resolved the Gateway Key (if any) and
    # stashed its id on request.state — reuse it instead of a second DB hit.
    gateway_key_id = getattr(request.state, "gateway_key_id", None)
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
    (see aigw.tokenizer.estimate_request_tokens) — so there is nothing for a
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
