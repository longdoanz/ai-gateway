"""
Model override rule matching, shared by kiro.nine_router_client's 9router
model override feature (the only override mechanism left — see
kiro.dashboard.routes_config for the DB-backed config it reads).

Rule matching: case-insensitive substring on normalized model name, first match wins.
Default model is applied when enabled but no rule matches.
"""

import json
from dataclasses import dataclass, field
from typing import List

from loguru import logger


def _parse_rules(raw: str) -> list:
    try:
        rules = json.loads(raw)
        return rules if isinstance(rules, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


@dataclass(frozen=True)
class OverrideConfig:
    enabled: bool
    rules: List[dict] = field(default_factory=list)
    default_model: str = "auto"
    # When True, `default_model` is enforced even if it is the literal string
    # "auto" (which is a real model name in 9router, not just a pass-through
    # sentinel). Global override leaves this False so an unset "auto" default
    # means "no enforcement".
    has_default: bool = False


def _normalize_targets(rule: dict) -> List[str]:
    """
    Normalize a rule's `to` field into an ordered list of target models.

    Accepts the legacy single-target form (``"to": "model"``) and the new
    multi-level form (``"to": ["model1", "model2"]``). Empty / non-string
    entries are dropped. Returns an empty list when no target is configured.

    Args:
        rule: A single override rule dict.

    Returns:
        Ordered list of non-empty target model strings.
    """
    raw = rule.get("to")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if isinstance(t, str) and t.strip()]
    return []


def resolve_models(model: str, config: OverrideConfig) -> List[str]:
    """
    Pure function — no I/O. Returns the ordered list of candidate models to try.

    The list is the failover order: the first entry is tried first, and each
    subsequent entry is a fallback used when the upstream call for the previous
    entry fails.

    Normalizes model to lowercase, iterates rules (first substring match wins).
    A matching rule yields its ordered targets (legacy single ``to`` or new
    multi-level ``to`` list). With no matching rule, the default is applied when
    configured; otherwise the original model is passed through unchanged.

    Args:
        model: The original (client-supplied) model name.
        config: The override configuration.

    Returns:
        Ordered list of one or more candidate model names.
    """
    if not config.enabled:
        return [model]

    from kiro.model_resolver import normalize_model_name
    normalized = normalize_model_name(model).lower()

    for rule in config.rules:
        from_pattern = (rule.get("from") or "").lower().strip()
        if from_pattern and from_pattern in normalized:
            targets = _normalize_targets(rule)
            if not targets:
                targets = [model]
            if model != targets[0]:
                logger.debug(f"Model override rule '{from_pattern}': {model} -> {targets}")
            return targets

    # No rule matched — apply default.
    # `default` may be the literal model name "auto" (a real model in 9router),
    # so we only skip the default when it was never configured (has_default=False
    # and the resolved value is empty/"auto").
    default = config.default_model or "auto"
    if config.has_default or default != "auto":
        if model != default:
            logger.debug(f"Model override default: {model} -> {default}")
            return [default]

    return [model]


def resolve_model(model: str, config: OverrideConfig) -> str:
    """
    Pure function — no I/O. Returns the single overridden model name.

    Backward-compatible wrapper around :func:`resolve_models` that returns only
    the first (highest-priority) candidate. Existing callers that rewrite a
    model string once keep working unchanged; multi-level failover callers use
    :func:`resolve_models` directly.
    """
    return resolve_models(model, config)[0]
