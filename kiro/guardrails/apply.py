# -*- coding: utf-8 -*-

"""
Span substitution: resolve overlapping findings, then rewrite the text once.

This replaces presidio's ``AnonymizerEngine``, which was measured to be
quadratic in the number of spans. On a fixed 29KB text, going from 25 to 800
spans (32x) took 0.73ms to 225ms — 308x, or 29us to 282us *per span*. On a
real ``git log`` payload (477 author emails in 213K chars) presidio spent
132.6ms against 11.5ms for the detection that fed it.

The replacement is one sort plus one pass: a 213K/477-span payload that cost
132.6ms now costs well under a millisecond.

Overlap policy: at a given start offset the longest span wins, and a span
contained in an already-accepted one is dropped. Two spans that *cross* — the
second starts inside the first and ends after it — are merged into one span
covering both. Presidio instead split the crossing span and emitted a second
placeholder for its tail; merging is the safer choice for a guard, because the
alternative considered (dropping the crossing span) would have let the part of
a detected value that sticks out past the first span through in plaintext.
A differential run over 3000 random overlap layouts found presidio and this
function agree except on those crossing cases, which the live patterns do not
produce: every numeric pattern is anchored on ``\\b`` at the same digit run, and
the one genuine EMAIL/IPV4 overlap (``admin@8.8.8.8``) is containment, not
crossing. The merge is there so a future pattern cannot turn that into a leak.
"""

from typing import Callable, Iterable

from kiro.guardrails.findings import Finding


def resolve_overlaps(findings: Iterable[Finding]) -> list[Finding]:
    """Resolve overlapping spans, preferring the longest match at each position."""
    ordered = sorted(findings, key=lambda f: (f.start, -(f.end - f.start)))
    kept: list[Finding] = []
    for f in ordered:
        if not kept or f.start >= kept[-1].end:
            kept.append(f)
            continue
        if f.end > kept[-1].end:
            # Crossing overlap: widen rather than discard, so no part of a
            # detected value survives into the forwarded text.
            last = kept[-1]
            kept[-1] = Finding(last.entity_type, last.start, f.end)
        # Otherwise f is fully contained in kept[-1] and is already covered.
    return kept


def apply_findings(
    text: str,
    findings: Iterable[Finding],
    render: Callable[[str, str], str],
) -> tuple[str, int]:
    """
    Rewrite ``text``, replacing each finding with ``render(entity_type, matched)``.

    Args:
        text: The original string.
        findings: Spans to replace; overlaps are resolved here.
        render: Called with (entity_type, matched_text), returns the replacement.

    Returns:
        (rewritten_text, replacement_count)
    """
    kept = resolve_overlaps(findings)
    if not kept:
        return text, 0

    out = []
    pos = 0
    for f in kept:
        out.append(text[pos:f.start])
        out.append(render(f.entity_type, text[f.start:f.end]))
        pos = f.end
    out.append(text[pos:])
    return "".join(out), len(kept)
