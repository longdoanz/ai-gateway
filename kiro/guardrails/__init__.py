# -*- coding: utf-8 -*-

"""
PII guardrail for outbound prompts.

Request path: detect (gated regex) → substitute surrogates → forward.
Response path: restore surrogates from the per-request vault as frames stream
back. No third-party dependency — see ``scrubber.py`` for why presidio was
dropped after being measured.

Wired into ``forward_to_nine_router`` — the one place that owns both the
request body and the response stream — rather than into each of the four
route call sites.
"""

import time
from typing import NamedTuple

from loguru import logger

from kiro.guardrails.restore import SseRestorer, restore_bytes, restore_stream
from kiro.guardrails.scrubber import SecretFound, anonymize_payload
from kiro.guardrails.vault import PiiVault

__all__ = [
    "PiiPolicy",
    "PiiVault",
    "ScrubResult",
    "SecretFound",
    "SseRestorer",
    "anonymize_payload",
    "get_pii_policy",
    "invalidate_pii_guard_cache",
    "restore_bytes",
    "restore_stream",
    "scrub_request",
]


class PiiPolicy(NamedTuple):
    """The three switches that decide what the guard does to a request."""

    mode: str                 # "off" | "tokenize" | "redact"
    secret_action: str        # "off" | "warn" | "block"
    restore_tool_args: bool


class ScrubResult(NamedTuple):
    """What the request side hands to the response side."""

    body: bytes
    vault: PiiVault | None
    restore_tool_args: bool


# Resolved policy, cached in-process. Mirrors the 9router model-override cache
# in ``nine_router_client``: read once, invalidated when the dashboard writes.
# Unlike that one it also expires, because this is a kill switch: the worst
# failure is flipping it off and having it stay on. The gateway runs a single
# uvicorn worker today, so the invalidation below is exact and immediate; the
# TTL is what keeps the switch converging if that ever stops being true.
_POLICY_TTL_SECONDS = 30
_policy_cache: PiiPolicy | None = None
_policy_fetched_at: float = 0.0

_VALID_MODES = ("off", "tokenize", "redact")
_VALID_SECRET_ACTIONS = ("off", "warn", "block")


def invalidate_pii_guard_cache() -> None:
    """Drop the cached policy so the next request re-reads it from the database."""
    global _policy_cache
    _policy_cache = None


async def get_pii_policy() -> PiiPolicy:
    """
    Resolve the guard policy: the dashboard setting wins, ``.env`` is the floor.

    The dashboard stores these in ``system_config`` so the guard can be turned
    off from the UI without a restart — which is the whole point of having a
    switch: a bug in it has to be stoppable while traffic is flowing.

    When the database is unreachable, has no row yet, or holds a value this
    build does not recognise, the ``.env`` value stands. That direction is
    deliberate: a database outage must never switch the guard *on* by surprise,
    and the gateway-only docker-compose has no database at all.
    """
    global _policy_cache, _policy_fetched_at
    now = time.monotonic()
    if _policy_cache is not None and now - _policy_fetched_at < _POLICY_TTL_SECONDS:
        return _policy_cache

    from kiro.config import PII_GUARD_MODE, PII_RESTORE_TOOL_ARGS, PII_SECRET_ACTION

    mode, secret_action = PII_GUARD_MODE, PII_SECRET_ACTION
    restore_tool_args = PII_RESTORE_TOOL_ARGS
    try:
        from kiro.db.engine import async_session_factory
        from kiro.db.repositories import get_config

        async with async_session_factory() as session:
            raw_mode = await get_config(session, "pii_guard_mode")
            raw_secret = await get_config(session, "pii_secret_action")
            raw_tool_args = await get_config(session, "pii_restore_tool_args")
        if raw_mode and raw_mode.lower() in _VALID_MODES:
            mode = raw_mode.lower()
        if raw_secret and raw_secret.lower() in _VALID_SECRET_ACTIONS:
            secret_action = raw_secret.lower()
        if raw_tool_args:
            restore_tool_args = raw_tool_args.lower() in ("true", "1", "yes")
    except Exception as exc:
        logger.debug(f"PII guard: no database policy, using .env ({exc})")

    _policy_cache = PiiPolicy(mode, secret_action, restore_tool_args)
    _policy_fetched_at = now
    return _policy_cache


async def scrub_request(body: bytes) -> ScrubResult:
    """
    Apply the configured guard policy to an outbound request body.

    Returns:
        ScrubResult — ``vault`` is None when the guard is off or in redact mode
        (nothing to restore), and ``body`` is returned unchanged when no entity
        matched. ``restore_tool_args`` is carried along so the response side
        does not resolve the policy a second time, and so both directions of
        one request are governed by the same snapshot of it.

    Raises:
        SecretFound: When credential material is present and the secret action
            is ``block``. Callers must turn this into a 400 without retrying.
    """
    policy = await get_pii_policy()
    if policy.mode not in ("tokenize", "redact"):
        return ScrubResult(body, None, policy.restore_tool_args)

    from kiro.config import PII_ENTITIES

    redact_only = policy.mode == "redact"
    scrubbed, vault = anonymize_payload(
        body,
        entities=PII_ENTITIES,
        redact_only=redact_only,
        secret_action=policy.secret_action,
    )
    return ScrubResult(
        scrubbed,
        vault if vault and not redact_only else None,
        policy.restore_tool_args,
    )
