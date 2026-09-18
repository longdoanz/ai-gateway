# -*- coding: utf-8 -*-

"""
Request-side anonymization.

This started on presidio's ``AnonymizerEngine`` and moved off it for one
measured reason: the engine is quadratic in the number of spans. On a fixed
29KB text, 25 → 800 spans (32x) cost 0.73ms → 225ms (308x), i.e. 29us → 282us
per span. A real ``git log`` payload — 477 author emails in 213K chars, which
is ordinary coding-agent traffic — spent 132.6ms inside presidio against
11.5ms for the detection feeding it.

What the engine did that matters is span-conflict resolution, and that is 30
lines (``kiro/guardrails/apply.py``) running in one sorted pass. Nothing else
it offered was used here: its ``DeanonymizeEngine`` cannot restore a ``custom``
operator's output at all, and its ``encrypt`` operator is non-deterministic,
inflates text ~2.4x and raises on any alteration of its base64.
"""

import json
from typing import Any, Iterator

from loguru import logger

from kiro.guardrails.apply import apply_findings
from kiro.guardrails.detector import detect
from kiro.guardrails.vault import PiiVault

# Keys whose string values are model-visible prose. Tool *schemas*
# (tools[].function.description) are excluded on purpose: they are static
# developer text with no user PII, and rewriting them would change the
# contract the model is being asked to honour.
_TEXT_KEYS = frozenset({"content", "text", "arguments", "thinking"})

# Subtrees that carry user content. Everything else in the payload (model,
# temperature, tools, metadata) is left byte-identical.
_SCANNED_ROOTS = ("messages", "system", "prompt", "input")


class SecretFound(Exception):
    """Raised when a credential is detected in a payload that must not be forwarded."""

    def __init__(self, entity_types: list[str]) -> None:
        self.entity_types = entity_types
        super().__init__(f"secret material detected: {', '.join(sorted(set(entity_types)))}")


def _iter_text_slots(node: Any) -> Iterator[tuple[Any, Any, str]]:
    """Yield (container, key, value) for every model-visible string in a subtree."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                if k in _TEXT_KEYS:
                    yield node, k, v
            else:
                yield from _iter_text_slots(v)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            if isinstance(item, str):
                # A bare string inside e.g. messages[].content list form.
                yield node, i, item
            else:
                yield from _iter_text_slots(item)


def anonymize_payload(
    body: bytes,
    entities: frozenset,
    redact_only: bool = False,
    secret_action: str = "warn",
) -> tuple[bytes, PiiVault]:
    """
    Tokenize PII in a JSON request body.

    Args:
        body: Raw request bytes. Non-JSON bodies are returned untouched.
        entities: PII entity types to tokenize.
        redact_only: Emit type-only markers (``<<EMAIL>>``) and no vault, so
            nothing is restored on the way back.
        secret_action: ``"block"`` raises, ``"warn"`` logs and forwards,
            ``"off"`` skips the check entirely.

    Returns:
        (body, vault) — the rewritten body, and the vault needed to restore
        the response. An empty vault means nothing was replaced and the body
        is the original object.

    Raises:
        SecretFound: When ``secret_action`` is ``"block"`` and a credential
            is detected.
    """
    vault = PiiVault()
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body, vault
    if not isinstance(payload, dict):
        return body, vault

    secrets: list[str] = []
    replacements = 0

    def render(entity_type: str, matched: str) -> str:
        if redact_only:
            return f"<<{entity_type}>>"
        return vault.token_for(entity_type, matched)

    for root in _SCANNED_ROOTS:
        subtree = payload.get(root)
        if subtree is None:
            continue
        for container, key, text in list(_iter_text_slots(subtree)):
            findings, found_secrets = detect(text, entities)
            if found_secrets and secret_action != "off":
                secrets.extend(found_secrets)
                if secret_action == "block":
                    # Continuing is pointless — nothing gets forwarded.
                    raise SecretFound(secrets)
            if not findings:
                continue
            container[key], n = apply_findings(text, findings, render)
            replacements += n

    if secrets:
        # Values are never logged, only their types.
        logger.warning(
            f"PII guard: request carries credential material {sorted(set(secrets))} "
            "(forwarded — set PII_SECRET_ACTION=block to reject instead)"
        )

    if not replacements:
        return body, vault

    logger.info(f"PII guard: replaced {replacements} span(s) {vault.summary()}")
    return json.dumps(payload, separators=(",", ":")).encode("utf-8"), vault
