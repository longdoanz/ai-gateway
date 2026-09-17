#!/usr/bin/env python3
"""PreToolUse guard: block Bash commands that print secret *values*.

Motivated by a real incident: `docker compose config` interpolates env_file /
.env into plaintext and dumped every prod secret into the transcript. This is a
last line of defense — it blocks the known command shapes so an accidental
invocation fails loudly instead of leaking. Counting/validating forms stay
allowed, so the safe habit is the path of least resistance.

Exit 0 = allow. Exit 2 = block (stderr is fed back as the reason).
Fail-open: any parse problem allows the command, so a broken hook never wedges
the session.
"""
import json
import re
import sys

# --- helpers ---------------------------------------------------------------

# A pipe into a counter never prints values, e.g. `cat .env | wc -l`.
SAFE_PIPE = re.compile(r"\|\s*(wc\b|grep\s+(-c|--count)\b)")
# A count-only or key-name-only grep prints no values.
SAFE_GREP = re.compile(
    r"grep\s+(-c|--count)\b"                    # count matches, print no values
    r"|grep\s+-\w*o\w*\s+['\"][^'\"]*=[^'\"]*['\"]"  # -o on a key-shaped (…=) pattern
)
ENV_FILE = re.compile(r"(?<![\w.-])(\.env(?:[._][\w-]+)?)(?![\w.-])")
ENV_SAFE_EXT = {"example", "sample", "template", "dist", "ci", "test"}
# Extraction that yields only KEY names, never the `=value` half: the
# `=`-separated first field. The awk form must pin `-F=` and print only `$1`;
# bare `awk '{print $1}'` splits on whitespace and would echo whole lines.
KEY_EXTRACT = re.compile(
    r"awk\b[^|;&]*-F\s*['\"]?=[^|;&]*\{\s*print\s+\$1\s*\}"
    r"|cut\b[^|;&]*-d\s*['\"]?=['\"]?[^|;&]*-f\s*1\b"
)
READER = re.compile(
    r"\b(cat|bat|less|more|head|tail|sed|awk|grep|rg|source|xxd|od|strings|"
    r"vi|vim|nano|emacs|diff|tee|cp|docker\s+cp)\b"
)
# Names whose value is a credential — catches `echo "$X"` / `printenv X`.
# Letter boundaries so a keyword only counts as a whole word: `$KEYBOARD_LAYOUT`
# and `$SECRETARY` are not credentials, but `$API_KEY` / `$JWT_SECRET` are.
SECRET_NAME = re.compile(
    r"(?<![A-Za-z])(?:PASS(?:WORD)?|SECRET|TOKEN|KEY|ENCRYPT|CREDENTIAL|"
    r"DATABASE_URL|REDIS_URL|DSN)(?![A-Za-z])",
    re.IGNORECASE,
)
ECHO = re.compile(r"\b(echo|printf)\b")
NAME_DEREF = re.compile(r"\$(?:\{)?[A-Za-z_][A-Za-z0-9_]*")
DISCARD = re.compile(r">\s*/dev/null")


def live_env_files(cmd: str):
    """Return .env paths in the command that hold real secrets."""
    out = []
    for m in ENV_FILE.finditer(cmd):
        token = m.group(1)
        ext = token.split(".")[-1] if token.count(".") > 1 else None
        if ext in ENV_SAFE_EXT:
            continue
        out.append(token)
    return out


# --- rules -----------------------------------------------------------------
# Each: (name, matches, hint, is_safe). is_safe(cmd) -> True exempts the match.

def _compose_config_matches(cmd: str) -> bool:
    return bool(re.search(r"\bdocker\b[^|;&]*\bcompose\b[^|;&]*\bconfig\b", cmd))


def _compose_config_safe(cmd: str) -> bool:
    return "--no-interpolate" in cmd or "--quiet" in cmd or "-q" in cmd.split()


def _inspect_matches(cmd: str) -> bool:
    return bool(re.search(r"\bdocker\s+inspect\b", cmd))


def _inspect_safe(cmd: str) -> bool:
    return "--format" in cmd or re.search(r"(^|\s)-f(\s|$)", cmd) is not None


def _env_dump_matches(cmd: str) -> bool:
    return bool(re.search(r"(^|[;&|]\s*)(env|printenv)\s*(#.*)?$", cmd))


def _printenv_named_matches(cmd: str) -> bool:
    return bool(re.search(r"\bprintenv\s+[\"']?[A-Za-z_][A-Za-z0-9_]*", cmd))


def _printenv_named_safe(cmd: str) -> bool:
    return bool(DISCARD.search(cmd))


def _echo_secret_matches(cmd: str) -> bool:
    return bool(ECHO.search(cmd)) and bool(NAME_DEREF.search(cmd)) and bool(SECRET_NAME.search(cmd))


def _env_file_matches(cmd: str) -> bool:
    return bool(live_env_files(cmd)) and bool(READER.search(cmd))


def _env_file_safe(cmd: str) -> bool:
    return bool(KEY_EXTRACT.search(cmd))


def _exec_env_matches(cmd: str) -> bool:
    # `env`/`printenv` as the spawned command, not the flag `--env` / `--env-file`
    # or a path segment ending in one: `docker run --env FOO=bar …`,
    # `docker run --env-file .env.example …` and a bind mount of an `env.py`
    # (`docker run -v /repo/alembic/env.py:/app/alembic/env.py …`) are all legit.
    # The lookarounds exclude a preceding or trailing path/word character, so a
    # bare `env`/`printenv` argument still matches but `…/env.py` does not.
    # `compose exec` is included — it spawns a process in the container just as
    # `docker exec` does, and dumps the same environment.
    return bool(
        re.search(
            r"\bdocker(\s+compose)?\s+(exec|run)\b[^|;&]*?(?<![\w./-])(env|printenv)\b(?![\w./-])",
            cmd,
        )
    )


RULES = [
    (
        _compose_config_matches,
        "`docker compose config` interpolates .env/.env_prod into plaintext secrets.",
        "Use `docker compose config --no-interpolate` (validates shape, keeps ${VARS} "
        "literal) or `--quiet` (validates only).",
        _compose_config_safe,
    ),
    (
        _inspect_matches,
        "`docker inspect` prints Config.Env — every env var, including secrets.",
        "Select only the fields you need, e.g. `docker inspect --format '{{.State.Status}}' <name>`.",
        _inspect_safe,
    ),
    (
        _env_dump_matches,
        "`env` / `printenv` dumps the whole environment.",
        "Check presence without the value: `printenv NAME >/dev/null && echo set`.",
        None,
    ),
    (
        _printenv_named_matches,
        "`printenv NAME` prints that variable's value, which may be a secret.",
        "Check presence: `printenv NAME >/dev/null && echo set` (redirect to /dev/null to allow).",
        _printenv_named_safe,
    ),
    (
        _echo_secret_matches,
        "`echo`/`printf` of a credential-shaped variable prints its value.",
        "Avoid echoing secrets; compare or redirect instead, e.g. `test -n \"$TOKEN\" && echo set`.",
        None,
    ),
    (
        _env_file_matches,
        "Reading a live .env file prints secret values into the transcript.",
        "Read key names only: `grep -o '^[A-Z_]*=' <file>` (count with `| wc -l`).",
        _env_file_safe,
    ),
    (
        _exec_env_matches,
        "`docker exec … env` prints the container's environment.",
        "Read a specific non-secret value, or use `--format` on inspect.",
        None,
    ),
]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd or SAFE_PIPE.search(cmd) or SAFE_GREP.search(cmd):
        return 0

    for matches, why, hint, is_safe in RULES:
        if not matches(cmd):
            continue
        if is_safe and is_safe(cmd):
            continue
        print(f"BLOCKED: {why}\n{hint}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
