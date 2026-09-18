# -*- coding: utf-8 -*-

"""
Fast entity detection feeding presidio's ``AnonymizerEngine``.

We do *not* use ``presidio-analyzer``: its value over regex is spaCy NER for
PERSON/LOCATION, which costs seconds on a 600KB payload and, being trained on
English, misses Vietnamese names anyway. ``Finding`` keeps the same shape its
``RecognizerResult`` has, so an analyzer could still be plugged in later.

Detection results are cached by content digest. Clients resend the whole
conversation verbatim every turn, so without a cache turn 30 pays to rescan
the same 29 turns. With it, only genuinely new text is ever scanned
(measured: ~0.02ms for a new turn vs ~8.5ms for a cold 588KB payload).
"""

import hashlib
import re
from collections import OrderedDict
from threading import Lock

from kiro.guardrails.findings import Finding
from kiro.guardrails.patterns import (
    DIGIT_GATE,
    LITERAL_PII,
    LITERAL_SECRETS,
    NUMERIC_GATE_PAD,
    NUMERIC_PII,
    SECRET_VALIDATORS,
    VALIDATORS,
    secret_scan_windows,
    shannon_entropy,
)
from kiro.guardrails.secret_rules import GITLEAKS_ALLOW_PATTERNS, GITLEAKS_STOPWORDS

# Spans are small; the cache holds digests and tuples, never the source text,
# so a few thousand entries stay well under a megabyte.
_CACHE_MAX = 8192
_cache: "OrderedDict[bytes, tuple]" = OrderedDict()
_cache_lock = Lock()

_stats = {"hits": 0, "misses": 0}


def cache_stats() -> dict:
    """Return a copy of the detector cache counters (for /health or tests)."""
    return dict(_stats, size=len(_cache))


def reset_cache() -> None:
    """Drop all cached detections. Tests use this; production never needs it."""
    with _cache_lock:
        _cache.clear()
    _stats["hits"] = _stats["misses"] = 0


def _scan(text: str, entities: frozenset) -> tuple:
    """Run the gated pattern set over one string. Returns (type, start, end) tuples."""
    found: list[tuple[str, int, int]] = []

    for entity_type, literal, pattern in LITERAL_PII:
        if entity_type in entities and literal in text:
            for m in pattern.finditer(text):
                found.append((entity_type, m.start(), m.end()))

    numeric = [(e, p) for e, p in NUMERIC_PII if e in entities]
    if numeric:
        for gate in DIGIT_GATE.finditer(text):
            # The gate only finds digit runs; a pattern may need characters
            # just outside it, so widen the span before the real scan.
            lo = max(0, gate.start() - NUMERIC_GATE_PAD)
            hi = min(len(text), gate.end() + NUMERIC_GATE_PAD)
            span = text[lo:hi]
            for entity_type, pattern in numeric:
                validator = VALIDATORS.get(entity_type)
                for m in pattern.finditer(span):
                    if validator is not None and not validator(m.group()):
                        continue
                    found.append((entity_type, lo + m.start(), lo + m.end()))

    return tuple(found)


def _scan_secrets(text: str) -> tuple:
    """Find credential material against the vendored gitleaks ruleset.

    Every rule's regex is a candidate only. Three gates decide whether a
    candidate is actually reported, in order from cheapest to most
    expensive: gitleaks' own entropy floor and allowlist/stopword data (data
    that ships with the rule, no per-project tuning), then this project's
    own SECRET_VALIDATORS (kiro/guardrails/patterns.py) for the handful of
    entity types that need a real semantic check (a JWT that actually
    decodes, a PEM block that actually has key material).

    With 220 rules, running every rule's regex over the whole payload would
    cost `rules x bytes` the same way NUMERIC_PII would without DIGIT_GATE.
    It is not enough to just skip rules whose keyword never appears, though:
    a handful of gitleaks' broader rules key off common English words
    ("key", "token", "secret", ...), and a payload full of ordinary prose or
    commit messages can hit those thousands of times. Running even a cheap
    rule's regex over the *whole* text once per hit is still `hits x bytes`.
    secret_scan_windows() (patterns.py) turns each hit into a small, merged
    window instead, so a rule only ever pays for the text actually near one
    of its keyword's occurrences — see its docstring for the measured
    difference this makes (a git-log-shaped 587KB payload went from ~1.3s to
    within budget once windowing replaced whole-text scanning).
    """
    found: list[tuple[str, int, int]] = []
    # Lower-casing 588KB is itself not free (measured separately from the
    # gate) — do it exactly once per scan regardless of how many rules end
    # up running against the original-case `text`.
    lowered = text.lower()
    for idx, windows in secret_scan_windows(lowered).items():
        rule = LITERAL_SECRETS[idx]
        validator = SECRET_VALIDATORS.get(rule.entity_type)
        for lo, hi in windows:
            # pos/endpos (not text slicing) so ``\b``/``^``/``$`` still see
            # the real characters just outside the window instead of an
            # artificial string edge.
            for m in rule.pattern.finditer(text, lo, hi):
                secret_value = m.group(rule.secret_group) if rule.secret_group else m.group()
                if secret_value is None:
                    # An optional group in the pattern didn't participate in
                    # this particular match; nothing to validate against.
                    continue
                if rule.min_entropy is not None and shannon_entropy(secret_value) < rule.min_entropy:
                    continue
                if secret_value.lower() in GITLEAKS_STOPWORDS:
                    continue
                if any(a.search(secret_value) for a in GITLEAKS_ALLOW_PATTERNS):
                    continue
                if any(a.search(secret_value) for a in rule.allow):
                    continue
                if validator is not None and not validator(secret_value, text, m.start(), m.end()):
                    continue
                found.append((rule.entity_type, m.start(), m.end()))
    return tuple(found)


def _digest(text: str, entities: frozenset) -> bytes:
    h = hashlib.blake2b(digest_size=16)
    h.update(repr(sorted(entities)).encode())
    h.update(b"\x00")
    h.update(text.encode("utf-8", errors="ignore"))
    return h.digest()


def detect(text: str, entities: frozenset) -> tuple[list[Finding], list[str]]:
    """
    Detect PII and secrets in one string.

    Args:
        text: The string to scan.
        entities: PII entity types to look for. Secrets are always scanned —
            blocking a leaked credential is not something a policy toggles off
            per entity.

    Returns:
        (pii_findings, secret_types) — spans of PII to tokenize, and the
        distinct secret entity types found (values are deliberately not
        returned, so a leaked key cannot reach a log line).
    """
    if not text:
        return [], []

    key = _digest(text, entities)
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            _stats["hits"] += 1
            pii_spans, secret_types = cached
            return [Finding(*t) for t in pii_spans], list(secret_types)

    _stats["misses"] += 1
    pii_spans = _scan(text, entities)
    secret_types = tuple(sorted({e for e, _, _ in _scan_secrets(text)}))

    with _cache_lock:
        _cache[key] = (pii_spans, secret_types)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)

    return [Finding(*t) for t in pii_spans], list(secret_types)
