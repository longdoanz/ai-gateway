# -*- coding: utf-8 -*-

"""
Generator for ``kiro/guardrails/secret_rules.py``.

Gitleaks (https://github.com/gitleaks/gitleaks) ships a community-maintained
TOML ruleset of 200+ credential patterns. Hand-rolling and maintaining that
many regexes ourselves is not a good use of anyone's time, so this script
vendors gitleaks' ruleset instead: it downloads one pinned release's
``config/gitleaks.toml``, translates every rule's Go/RE2 regex into a Python
``re`` pattern, and writes the result to a plain, importable Python module.

Why vendor instead of depending on gitleaks at runtime
-------------------------------------------------------
Gitleaks is a Go binary; there is no way to call its regex engine from this
Python service without shelling out per request, which is a non-starter on
the request hot path. RE2 and Python's ``re`` are different engines with
different syntax quirks (see "Known regex translation issues" below), so the
translation has to happen once, offline, with a human able to look at what
got dropped — not silently at import time.

Usage
-----
    python3 scripts/gen_secret_rules.py

Regenerate whenever gitleaks cuts a new release (check quarterly — the
ruleset is actively maintained and new credential formats are added often):

1. Bump ``GITLEAKS_VERSION`` below to the new tag.
2. Run this script again. It prints a load/skip summary — read it. If a
   previously-loaded rule newly fails to compile, or the skip count jumps,
   investigate before committing.
3. Re-run the false-positive regression (see
   ``tests/unit/test_guardrails.py``) against this repo before committing —
   a wider ruleset without a re-check of it is worse than not upgrading.
4. Commit the regenerated ``kiro/guardrails/secret_rules.py`` alongside the
   version bump — it is checked into git; nothing reads the TOML at import
   time or over the network at runtime.

Known regex translation issues (RE2/Go -> Python ``re``)
----------------------------------------------------------
- Inline ``(?i)`` must be the very first thing in the pattern in Python 3.11+
  ("global flags not at the start of the expression"); gitleaks/Go allows it
  anywhere. Where a pattern has exactly one embedded ``(?i)`` not at the
  start, we lift it out and apply ``re.IGNORECASE`` to the whole pattern
  instead (this can make a previously case-sensitive prefix case-insensitive
  too — a deliberate, documented over-approximation, not a silent one).
- Scoped flag groups, ``(?i:...)`` and ``(?-i:...)``, are left alone: Python's
  ``re`` supports those natively.
- POSIX classes (``[:alnum:]``), atomic groups, possessive quantifiers, and a
  few other RE2/PCRE-only constructs have no Python ``re`` equivalent. Rules
  using them fail to compile and are skipped (see the generated file's
  ``SKIPPED_RULES`` for the exact list and reason).
- Path-only rules (gitleaks rules with a ``path`` matcher and no ``regex`` —
  e.g. ``pkcs12-file``) have nothing to run against a text payload and are
  skipped.
- Rules that also carry a ``path`` restriction (rule only applies to certain
  filenames) are loaded anyway, minus the path check — we scan JSON request
  fields, not files on disk, so there is no path to restrict on. This can
  only make such a rule fire in more places than gitleaks would, never fewer;
  the keyword + entropy + allowlist gates still apply.
"""

import re
import sys
import tomllib
import urllib.request
from pathlib import Path

# Pin to a specific release tag, never `master` — a moving target defeats the
# whole point of a reviewed, checked-in ruleset. Bump deliberately (see the
# regenerate steps above), not automatically.
GITLEAKS_VERSION = "v8.30.1"
GITLEAKS_GENERATED = "2026-09-18"

_TOML_URL = f"https://raw.githubusercontent.com/gitleaks/gitleaks/{GITLEAKS_VERSION}/config/gitleaks.toml"
_OUT_PATH = Path(__file__).resolve().parent.parent / "kiro" / "guardrails" / "secret_rules.py"

# gitleaks id -> entity_type, for the handful of rules this codebase already
# has second-stage validators for (kiro/guardrails/patterns.py
# SECRET_VALIDATORS). Keeping these names stable means those validators keep
# applying to the vendored rule without any change on the validator side.
# Everything else gets an entity_type derived mechanically from its id.
_ENTITY_OVERRIDES = {
    "anthropic-api-key": "ANTHROPIC_KEY",
    "openai-api-key": "OPENAI_KEY",
    "aws-access-token": "AWS_ACCESS_KEY",
    "private-key": "PRIVATE_KEY",
    "jwt": "JWT",
}

_INLINE_IGNORECASE = re.compile(r"\(\?i\)")
_GO_END_ANCHOR = "\\z"  # RE2/Go "absolute end of text" -> Python's \Z

# POSIX bracket expressions (e.g. "[:alnum:]") used inside a character class,
# as in RE2's `[[:alnum:]]`. Python's `re` has no such syntax — it silently
# parses the inner "[:alnum:]" as a *literal* nested character set (the
# characters ':', 'a', 'l', 'n', 'u', 'm'), which is not an error but is not
# remotely the same match either. `re.compile` only warns (FutureWarning),
# it does not raise, so this has to be caught explicitly before compiling or
# it would silently ship a wrong pattern instead of a skipped one.
_POSIX_BRACKET_CLASS = re.compile(r"\[:[a-z]+:\]")

_HEADER_TEMPLATE = '''# -*- coding: utf-8 -*-

"""
GENERATED FILE — do not hand-edit.

Vendored from gitleaks {version} (config/gitleaks.toml), generated on
{generated}. Regenerate with::

    python3 scripts/gen_secret_rules.py

Re-check quarterly (or whenever a new gitleaks release is worth pulling in) —
see the docstring of scripts/gen_secret_rules.py for the full procedure and
{skipped} for the current skip list. Do not edit the rule bodies below by
hand; fix the generator or the override tables in
scripts/gen_secret_rules.py and regenerate instead, or the next regeneration
silently reverts your change.

This module is plain Python data: no network access and no TOML parsing at
import time, so it costs nothing on the request hot path.

Rules loaded: {loaded} / {total} from upstream. Skipped: {n_skipped}
(reasons below, one per skipped rule id).

SKIPPED_RULES:
{skip_lines}
"""

import re
from typing import NamedTuple

# The pinned upstream release this file was generated from, and when. Kept
# as plain data (not just in the docstring) so a health check or test can
# report the live ruleset version without parsing this file's comments.
GITLEAKS_VERSION = {version!r}
GITLEAKS_GENERATED = {generated!r}


class SecretRule(NamedTuple):
    """One credential-detection rule, translated from a gitleaks TOML rule.

    Attributes:
        entity_type: Name surfaced to callers (SecretFound, logs). Stable
            across regenerations for the ids in _ENTITY_OVERRIDES so existing
            SECRET_VALIDATORS entries keep applying.
        keywords: Lowercase literal substrings; a rule is only a candidate if
            at least one of its keywords is present in the lowercased text
            (this is the single-pass gate _scan_secrets relies on).
        pattern: Compiled regex. Group 0 is the whole match; the secret value
            itself is in ``secret_group``.
        min_entropy: Minimum Shannon entropy (bits/char) the secret_group text
            must clear to count as a match, or None if the rule has no
            entropy floor. Mirrors gitleaks' `entropy` field.
        secret_group: Index of the capture group holding the credential value
            (0 = whole match, for patterns with no capture groups).
        allow: Per-rule allowlist regexes (gitleaks `[[rules.allowlists]]`).
            If any fully matches the secret_group text, the match is dropped
            — e.g. AWS's own "...EXAMPLE" doc placeholders.
    """

    entity_type: str
    keywords: tuple[str, ...]
    pattern: "re.Pattern[str]"
    min_entropy: float | None
    secret_group: int
    allow: "tuple[re.Pattern[str], ...]"


# Global gitleaks allowlist: text values these regexes fully match (template
# placeholders like "${{VAR}}", "%s", bare "true"/"false", example home-dir
# paths, ...) are never a real secret regardless of which rule matched them.
GITLEAKS_ALLOW_PATTERNS: "tuple[re.Pattern[str], ...]" = (
{allow_regexes}
)

# Global gitleaks stopwords (lowercased exact values that are never a secret,
# e.g. the well-known placeholder UUID gitleaks itself ships as a fixture).
GITLEAKS_STOPWORDS: frozenset = frozenset({{
{stopwords}
}})

GITLEAKS_SECRET_RULES: tuple[SecretRule, ...] = (
{rules}
)
'''


def _fetch_toml() -> bytes:
    """Download the pinned gitleaks TOML config.

    Returns:
        Raw TOML bytes.
    """
    with urllib.request.urlopen(_TOML_URL, timeout=30) as resp:  # noqa: S310 (pinned https URL)
        return resp.read()


def _entity_type(rule_id: str) -> str:
    """Derive an entity_type name from a gitleaks rule id.

    Args:
        rule_id: gitleaks rule ``id`` field, e.g. ``"1password-secret-key"``.

    Returns:
        The overridden name if one exists, else the id upper-cased with
        hyphens turned into underscores.
    """
    if rule_id in _ENTITY_OVERRIDES:
        return _ENTITY_OVERRIDES[rule_id]
    return rule_id.upper().replace("-", "_")


def _try_compile(regex: str) -> tuple[re.Pattern | None, str | None]:
    """Compile one gitleaks regex as Python ``re``, fixing what's fixable.

    Two RE2/Go idioms have no direct Python ``re`` equivalent and are
    rewritten before giving up:

    - ``(?i)`` anywhere but the very start of the pattern is a hard error on
      Python 3.11+ ("global flags not at the start of the expression"), but
      in RE2 it simply turns on case-insensitivity for the remainder of the
      enclosing group — which is exactly what a *global* ``re.IGNORECASE``
      does too. So every ``(?i)`` marker is stripped and, if any were
      present, ``re.IGNORECASE`` is applied to the whole pattern instead.
      Scoped ``(?-i:...)`` groups (used to carve out a case-sensitive
      island inside an otherwise case-insensitive rule) are untouched by
      this and keep working, since Python respects local flag groups
      whether the surrounding case-insensitivity came from a leading
      ``(?i)`` or from the ``re.IGNORECASE`` compile flag.
    - ``\\z`` (RE2 "absolute end of text") is not a valid Python ``re``
      escape; Python's ``\\Z`` means the same thing, so it is substituted.

    Args:
        regex: The raw RE2-flavoured pattern string from the TOML.

    Returns:
        (pattern, skip_reason) — exactly one is not None. ``pattern.pattern``
        holds the (possibly rewritten) source actually compiled, which is
        what gets embedded in the generated file — never the raw upstream
        text — so regenerating twice in a row is idempotent.
    """
    if _POSIX_BRACKET_CLASS.search(regex):
        return None, "uses a POSIX bracket expression (e.g. [:alnum:]) that Python re mis-parses as a literal nested set, not a character class"

    candidates: list[tuple[str, int]] = [(regex, 0)]
    if _INLINE_IGNORECASE.search(regex):
        candidates.append((_INLINE_IGNORECASE.sub("", regex), re.IGNORECASE))
    for pat, flags in list(candidates):
        if _GO_END_ANCHOR in pat:
            candidates.append((pat.replace(_GO_END_ANCHOR, "\\Z"), flags))

    last_err: re.error | None = None
    for pat, flags in candidates:
        try:
            return re.compile(pat, flags), None
        except re.error as e:
            last_err = e
    return None, str(last_err)


def _rule_literal(rule_id: str, entity_type: str, keywords: tuple[str, ...],
                   pattern: re.Pattern, min_entropy: float | None,
                   secret_group: int, allow: tuple[re.Pattern, ...]) -> str:
    """Render one SecretRule as a Python source literal for the generated file."""
    allow_src = ", ".join(f"re.compile({a.pattern!r}, {a.flags!r})" for a in allow)
    if allow_src:
        allow_src += ","
    return (
        f"    SecretRule(  # {rule_id}\n"
        f"        entity_type={entity_type!r},\n"
        f"        keywords={keywords!r},\n"
        f"        pattern=re.compile({pattern.pattern!r}, {pattern.flags!r}),\n"
        f"        min_entropy={min_entropy!r},\n"
        f"        secret_group={secret_group!r},\n"
        f"        allow=({allow_src}),\n"
        f"    ),"
    )


def main() -> None:
    """Fetch, translate, and write the vendored ruleset. Prints a summary."""
    raw = _fetch_toml()
    doc = tomllib.loads(raw.decode("utf-8"))

    rules = doc["rules"]
    total = len(rules)
    loaded_src: list[str] = []
    skipped: list[tuple[str, str]] = []
    seen_entities: dict[str, str] = {}

    for rule in rules:
        rule_id = rule["id"]
        regex = rule.get("regex")
        if not regex:
            skipped.append((rule_id, "path-only rule (no content regex) — not applicable to text scanning"))
            continue

        pattern, err = _try_compile(regex)
        if pattern is None:
            skipped.append((rule_id, f"does not compile as Python re: {err}"))
            continue

        entity_type = _entity_type(rule_id)
        if entity_type in seen_entities:
            skipped.append((
                rule_id,
                f"entity_type {entity_type!r} collides with rule {seen_entities[entity_type]!r}",
            ))
            continue
        seen_entities[entity_type] = rule_id

        keywords = tuple(sorted({k.lower() for k in rule.get("keywords", [])}))
        min_entropy = rule.get("entropy")
        num_groups = pattern.groups
        secret_group = rule.get("secretGroup")
        if secret_group is None:
            secret_group = 1 if num_groups >= 1 else 0
        if secret_group > num_groups:
            # Malformed relative to what compiled; fall back to the whole
            # match rather than crash at scan time on an out-of-range group.
            secret_group = 0

        allow_regexes: list[str] = []
        for allowlist in rule.get("allowlists", []):
            allow_regexes.extend(allowlist.get("regexes", []))
        compiled_allow: list[re.Pattern] = []
        bad_allow = False
        for a in allow_regexes:
            allow_pat, allow_err = _try_compile(a)
            if allow_pat is None:
                skipped.append((rule_id, f"per-rule allowlist regex does not compile: {allow_err}"))
                bad_allow = True
                break
            compiled_allow.append(allow_pat)
        if bad_allow:
            continue

        loaded_src.append(_rule_literal(
            rule_id, entity_type, keywords, pattern, min_entropy, secret_group, tuple(compiled_allow),
        ))

    global_allowlist = doc.get("allowlist", {})
    allow_regex_lines = []
    for a in global_allowlist.get("regexes", []):
        allow_pat, allow_err = _try_compile(a)
        if allow_pat is None:
            print(f"WARNING: global allowlist regex skipped, does not compile: {a!r}: {allow_err}", file=sys.stderr)
            continue
        allow_regex_lines.append(f"    re.compile({allow_pat.pattern!r}, {allow_pat.flags!r}),")

    stopword_lines = [f"    {s!r}," for s in global_allowlist.get("stopwords", [])]

    skip_lines = "\n".join(f"- {rid}: {reason}" for rid, reason in skipped) or "- (none)"

    header = _HEADER_TEMPLATE.format(
        version=GITLEAKS_VERSION,
        generated=GITLEAKS_GENERATED,
        skipped="this module's SKIPPED_RULES constant",
        loaded=len(loaded_src),
        total=total,
        n_skipped=len(skipped),
        skip_lines=skip_lines,
        allow_regexes="\n".join(allow_regex_lines) if allow_regex_lines else "",
        stopwords="\n".join(stopword_lines) if stopword_lines else "",
        rules="\n".join(loaded_src),
    )

    # SKIPPED_RULES is appended after the templated body so it is both in the
    # docstring (human-readable at a glance) and available as data (a test
    # or a future script can assert against it without parsing the header).
    skipped_const = "\nSKIPPED_RULES: tuple[tuple[str, str], ...] = (\n" + "\n".join(
        f"    ({rid!r}, {reason!r})," for rid, reason in skipped
    ) + "\n)\n"

    _OUT_PATH.write_text(header + skipped_const, encoding="utf-8")

    print(f"gitleaks {GITLEAKS_VERSION}: {total} rules in upstream TOML")
    print(f"  loaded:  {len(loaded_src)}")
    print(f"  skipped: {len(skipped)}")
    for rid, reason in skipped:
        print(f"    - {rid}: {reason}")
    print(f"wrote {_OUT_PATH}")


if __name__ == "__main__":
    main()
