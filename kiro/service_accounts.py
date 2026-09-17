# -*- coding: utf-8 -*-

"""
Service Account resolution and model-allowlist enforcement.

A Service Account is a non-human identity (CI bot, app, team) that is NOT
tied to a User. It authenticates with an ``izisa_``-prefixed API key and is
restricted to an admin-configured allowlist of models. Service-account
traffic always routes straight to 9router (see
``kiro.nine_router_client.forward_to_nine_router``), never the Kiro
account/key pool.

This module is deliberately independent of API_KEY_MODE: the resolver here
is consulted by ``kiro.routes_openai.verify_api_key`` and
``kiro.routes_anthropic.verify_anthropic_api_key`` *before* the
direct-9router / API_KEY_MODE / Kiro-pool branch split in
``chat_completions`` / ``messages``, so enforcement cannot be bypassed by an
admin flipping the direct-9router-mode runtime toggle.
"""

from dataclasses import dataclass, field

from loguru import logger

from kiro.db.repositories import SERVICE_ACCOUNT_KEY_PREFIX, decode_allowed_models, hash_api_key
from kiro.nine_router_client import OnUsage, _strip_context_window_suffix


@dataclass
class ServiceAccountContext:
    """Resolved identity for a request authenticated with an ``izisa_`` key.

    Attributes:
        id: Service account primary key.
        name: Human-readable, unique identifier.
        allowed_models: Admin-configured allowlist of model ids the account
            may use. An empty list means no models are allowed (fail-closed).
    """

    id: int
    name: str
    allowed_models: list[str] = field(default_factory=list)


def _is_db_configured() -> bool:
    """Return True when a database is available for service-account lookups.

    Unlike ``kiro.usage.scheduler.is_db_configured()``, this does NOT also
    require API_KEY_MODE — service accounts must resolve regardless of
    whether the gateway is in API_KEY_MODE, account-manager mode, or
    direct-9router mode.

    Returns:
        True if DATABASE_URL is configured (the async session factory
        exists), False otherwise.
    """
    from kiro.db.engine import async_session_factory
    return async_session_factory is not None


async def resolve_service_account(token: str | None) -> ServiceAccountContext | None:
    """Resolve a bearer/x-api-key token to a ServiceAccountContext, if it is one.

    Returns None immediately (without touching the database) when the token
    is missing, does not carry the ``izisa_`` prefix, or no database is
    configured. Never raises — on any unexpected error this logs at debug
    level and returns None, mirroring the defensive style of
    ``kiro.api_key_mode._resolve_gateway_key``.

    Args:
        token: Raw bearer/x-api-key token value from the incoming request.

    Returns:
        A ServiceAccountContext when `token` is an active ``izisa_`` key
        belonging to an active service account, otherwise None.
    """
    if not token or not token.startswith(SERVICE_ACCOUNT_KEY_PREFIX):
        return None
    if not _is_db_configured():
        return None
    try:
        from kiro.db.engine import async_session_factory
        from kiro.db.repositories import get_service_account_by_id, get_service_account_key_by_hash

        key_hash = hash_api_key(token)
        async with async_session_factory() as session:
            sa_key = await get_service_account_key_by_hash(session, key_hash)
            if sa_key is None:
                return None
            # Look up the account explicitly (rather than via the ORM
            # relationship) to avoid a lazy-load outside of an awaited
            # context on the async session.
            service_account = await get_service_account_by_id(session, sa_key.service_account_id)
            if service_account is None or not service_account.is_active:
                return None
            return ServiceAccountContext(
                id=service_account.id,
                name=service_account.name,
                allowed_models=decode_allowed_models(service_account.allowed_models),
            )
    except Exception as e:
        logger.debug(f"Service account resolution failed: {e}")
        return None


def is_model_allowed(model: str | None, allowed: list[str]) -> bool:
    """Check whether `model` matches an entry in a service account's allowlist.

    Matching is normalized to bridge the gap between 9router's catalog ids
    (``{alias}/{model}``, e.g. ``"kiro/claude-sonnet-4"``, ``"openai/gpt-5"``)
    and what a client actually sends (a bare model name, sometimes with a
    client-side context-window suffix like ``"claude-opus-5[1m]"``):

    - Both sides have any ``[1m]``/``[200k]``-style suffix stripped.
    - Comparison is case-insensitive.
    - An allowlist entry matches if its full id matches, OR the part after
      its first ``/`` matches the bare requested model, OR (the reverse) the
      part after the first ``/`` of a fully-prefixed *requested* model
      matches a bare allowlist entry.

    Fail-closed: an empty `allowed` list always returns False.

    Args:
        model: The model id requested by the client.
        allowed: The service account's admin-configured allowlist
            (as returned by ``kiro.db.repositories.decode_allowed_models``).

    Returns:
        True if `model` is permitted, False otherwise.
    """
    if not allowed or not model:
        return False

    requested = _strip_context_window_suffix(model) or ""
    requested_lower = requested.lower()
    if not requested_lower:
        return False

    requested_suffix = requested_lower.split("/", 1)[1] if "/" in requested_lower else None

    for entry in allowed:
        entry_stripped = _strip_context_window_suffix(entry) or ""
        entry_lower = entry_stripped.lower()
        if not entry_lower:
            continue
        if entry_lower == requested_lower:
            return True
        entry_suffix = entry_lower.split("/", 1)[1] if "/" in entry_lower else None
        # Allowlist entry is "{alias}/{model}", client sent the bare model.
        if entry_suffix is not None and entry_suffix == requested_lower:
            return True
        # Client sent the fully-prefixed form, allowlist entry is bare.
        if requested_suffix is not None and requested_suffix == entry_lower:
            return True

    return False


def make_service_account_usage_cb(service_account_id: int) -> OnUsage | None:
    """Build an on_usage callback for a service account's 9router traffic.

    Mirrors ``kiro.api_key_mode._make_nine_router_usage_cb``: records both
    the monthly request-count rollup (``ServiceAccountUsage``) and the daily
    per-model token usage (``ServiceAccountDailyUsage``). Tracking failures
    are logged and swallowed — they must never break the response.

    Args:
        service_account_id: The service account whose usage to record.

    Returns:
        An async callback of (input_tokens, output_tokens, model) -> None,
        or None when the database isn't configured (nothing to track).
    """
    if not _is_db_configured():
        return None

    async def _cb(input_tokens: int, output_tokens: int, model: str) -> None:
        import time

        from kiro.db.engine import async_session_factory
        from kiro.db.repositories import increment_service_account_daily_usage, increment_service_account_usage

        month = time.strftime("%Y-%m")
        today = time.strftime("%Y-%m-%d")
        try:
            async with async_session_factory() as session:
                await increment_service_account_usage(session, service_account_id, month, 1)
                await increment_service_account_daily_usage(
                    session, service_account_id, today, input_tokens, output_tokens, model=model
                )
        except Exception as e:
            logger.debug(f"Service account usage tracking failed: {e}")

    return _cb
