# -*- coding: utf-8 -*-

"""
Response-side restoration of surrogates back to the original values.

The hard part is streaming, and it is harder than it first looks. A surrogate
is several model tokens (``<<``, ``EMAIL``, ``_``, ``1``, ``>>``), and each SSE
frame carries roughly one token, so a surrogate is almost *always* split — not
across raw byte boundaries, but across separate JSON frames::

    data: {"choices":[{"delta":{"content":"mail <<EMA"}}]}

    data: {"choices":[{"delta":{"content":"IL_1>> da nhan"}}]}

Between ``<<EMA`` and ``IL_1>>`` sits protocol framing, so a byte-level carry
buffer can never rejoin them. Restoration therefore happens at the *delta*
level: frames are parsed, the text fields concatenated through a carry buffer,
and the frames re-serialized. A trailing fragment that might still grow into a
surrogate is withheld from the current frame and prepended to the next one —
delaying at most one surrogate's worth of characters.

Non-SSE bodies take the simple path: buffer and substitute once.

Restoration never fails a response. An unknown surrogate passes through
untouched rather than raising — unlike presidio's ``decrypt``, which raises
``Incorrect padding`` as soon as the model alters one character of its base64
ciphertext.
"""

import json
from typing import Any, AsyncIterator, Iterator

from loguru import logger

from kiro.guardrails.vault import TOKEN_RE, TOKEN_RE_BYTES, PiiVault

# Response keys whose string values are model-generated prose. Covers OpenAI
# (delta.content / message.content) and Anthropic (delta.text / content[].text)
# in both their streaming and non-streaming shapes.
_PROSE_KEYS = frozenset({"content", "text", "reasoning_content", "thinking"})

# Keys whose value is a fragment of *JSON source* rather than prose: the tool
# arguments the client will parse and execute — ``tool_calls[].function.
# arguments`` for OpenAI, ``delta.partial_json`` for Anthropic. These must be
# restored too, or the tool runs against the placeholder instead of the real
# value; the request side already tokenizes ``arguments`` on the way up. The
# restored value is being spliced into a JSON string literal that the client
# parses later, so it is escaped for that inner context first — otherwise an
# original containing a quote or backslash produces arguments the client
# cannot parse.
_JSON_ARG_KEYS = frozenset({"arguments", "partial_json"})


def _iter_text_slots(node: Any, slot: str = "") -> Iterator[tuple[Any, Any, str, str, bool]]:
    """
    Yield (container, key, value, slot_id, escape) for every restorable string.

    ``slot_id`` separates independently streamed runs of text. Parallel tool
    calls each carry their own ``index``, so a fragment withheld from one run
    is never released into another's arguments.
    """
    if isinstance(node, dict):
        index = node.get("index")
        if isinstance(index, int):
            slot = f"{slot}.{index}"
        for k, v in node.items():
            if isinstance(v, str):
                if k in _PROSE_KEYS:
                    yield node, k, v, slot, False
                elif k in _JSON_ARG_KEYS:
                    yield node, k, v, slot, True
            else:
                yield from _iter_text_slots(v, slot)
    elif isinstance(node, list):
        for item in node:
            if not isinstance(item, str):
                yield from _iter_text_slots(item, slot)


class _Carry:
    """Substitutes surrogates across a sequence of text fragments."""

    __slots__ = ("_vault", "_pending", "_window", "_escape", "restored", "unknown")

    def __init__(self, vault: PiiVault, escape: bool = False) -> None:
        self._vault = vault
        self._pending = ""
        # Longest prefix of a surrogate that could still be incomplete.
        self._window = max(vault.max_token_len - 1, 0)
        self._escape = escape
        self.restored = 0
        self.unknown = 0

    def _substitute(self, text: str) -> str:
        def repl(m):
            original = self._vault.original_for(m.group())
            if original is None:
                self.unknown += 1
                return m.group()
            self.restored += 1
            if self._escape:
                return json.dumps(original, ensure_ascii=False)[1:-1]
            return original

        return TOKEN_RE.sub(repl, text)

    def push(self, fragment: str) -> str:
        """Feed a fragment; return the part that is safe to emit now."""
        buf = self._substitute(self._pending + fragment)
        # A surrogate starts with "<<", so any "<" near the end may be the
        # beginning of one that has not fully arrived.
        start = max(0, len(buf) - self._window)
        idx = buf.find("<", start)
        if idx == -1:
            self._pending = ""
            return buf
        self._pending = buf[idx:]
        return buf[:idx]

    def drain(self) -> str:
        """Release whatever is still held back."""
        if not self._pending:
            return ""
        out = self._substitute(self._pending)
        self._pending = ""
        return out

    def __bool__(self) -> bool:
        return bool(self._pending)


class SseRestorer:
    """Frame-aware surrogate restoration for a Server-Sent Events stream."""

    __slots__ = ("_vault", "_carries", "_templates", "_buf", "_restore_tool_args")

    def __init__(self, vault: PiiVault, restore_tool_args: bool = True) -> None:
        self._vault = vault
        # One carry per independent run of text, keyed by (slot_id, escape):
        # prose and tool arguments interleave in the same stream and must not
        # share a buffer, and neither must two parallel tool calls.
        self._carries: dict[tuple[str, bool], _Carry] = {}
        # Shape of the last frame that fed each carry, reused to emit a final
        # frame if anything is still held back when the stream ends.
        self._templates: dict[tuple[str, bool], bytes] = {}
        self._buf = b""
        # False disables restoring _JSON_ARG_KEYS slots (tool-call arguments)
        # while prose keeps restoring normally — see PII_RESTORE_TOOL_ARGS.
        self._restore_tool_args = restore_tool_args

    def _carry_for(self, key: tuple[str, bool]) -> _Carry:
        carry = self._carries.get(key)
        if carry is None:
            carry = self._carries[key] = _Carry(self._vault, escape=key[1])
        return carry

    def _holding(self) -> bool:
        return any(self._carries.values())

    def _text_lines(self, frame: bytes) -> list[tuple[int, Any, list]]:
        """Find the data lines in a frame that carry model text.

        A frame is not identified by its first line: Anthropic streams put an
        ``event:`` line ahead of ``data:``, so the whole frame is inspected.
        Parsing here — before anything is consumed from the carry — lets the
        caller decide whether this frame advances the carry or must wait for it
        to be flushed first.
        """
        found = []
        for i, line in enumerate(frame.split(b"\n")):
            if not line.startswith(b"data:"):
                continue
            raw = line[5:].lstrip()
            if raw == b"[DONE]" or not raw:
                continue
            try:
                payload = json.loads(raw)
            except ValueError:
                continue
            slots = list(_iter_text_slots(payload))
            if not self._restore_tool_args:
                # escape=True marks a _JSON_ARG_KEYS slot (tool arguments).
                # Dropping it here means _restore_frame/_flush_frames never
                # see it, so it is never assigned to — the raw fragment
                # (surrogate still literal) passes through untouched.
                slots = [s for s in slots if not s[4]]
            if slots:
                found.append((i, payload, slots))
        return found

    def _restore_frame(self, frame: bytes, text_lines: list) -> bytes:
        """Restore one complete SSE frame, returning it re-serialized."""
        lines = frame.split(b"\n")
        for idx, payload, slots in text_lines:
            for container, key, text, slot, escape in slots:
                carry_key = (slot, escape)
                container[key] = self._carry_for(carry_key).push(text)
                self._templates[carry_key] = frame
            lines[idx] = b"data: " + json.dumps(
                payload, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        return b"\n".join(lines)

    def _flush_frames(self) -> bytes:
        """Emit synthetic frames carrying whatever the carries still hold."""
        out = []
        for carry_key, carry in self._carries.items():
            if not carry:
                continue
            template = self._templates.get(carry_key)
            if template is None:
                continue
            leftover = carry.drain()
            if not leftover:
                continue
            # Reuse the shape of the last frame that fed this carry — including
            # any "event:" line — so the client sees a frame it already parses.
            lines = template.split(b"\n")
            placed = False
            for idx, payload, slots in self._text_lines(template):
                for container, key, _text, slot, escape in slots:
                    if (slot, escape) == carry_key and not placed:
                        container[key] = leftover
                        placed = True
                    else:
                        # Other slots in the template frame already had their
                        # text delivered; emit them empty, not duplicated.
                        container[key] = ""
                lines[idx] = b"data: " + json.dumps(
                    payload, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
            if placed:
                out.append(b"\n".join(lines) + b"\n\n")
        return b"".join(out)

    def feed(self, chunk: bytes) -> bytes:
        self._buf += chunk
        if b"\n\n" not in self._buf:
            return b""
        *frames, self._buf = self._buf.split(b"\n\n")

        out = []
        for frame in frames:
            # Fast path: a surrogate always starts with "<", so a frame with no
            # "<" anywhere cannot contain or begin one. With nothing held back
            # it can be forwarded verbatim, skipping the parse/re-serialize that
            # would otherwise cost ~30us on every frame of every response.
            if not self._holding() and b"<" not in frame:
                out.append(frame + b"\n\n")
                continue

            text_lines = self._text_lines(frame)
            if text_lines:
                out.append(self._restore_frame(frame, text_lines) + b"\n\n")
                continue
            # A frame with no text slot ("[DONE]", a ping, an error envelope)
            # must not overtake text we are still holding back.
            flushed = self._flush_frames()
            if flushed:
                out.append(flushed)
            out.append(frame + b"\n\n")
        return b"".join(out)

    def flush(self) -> bytes:
        tail = self._buf
        self._buf = b""
        out = self._flush_frames()
        if tail:
            out += tail
        restored = sum(c.restored for c in self._carries.values())
        unknown = sum(c.unknown for c in self._carries.values())
        if unknown:
            logger.warning(
                f"PII guard: {restored} surrogate(s) restored, "
                f"{unknown} unrecognised (the model altered a token — "
                "it reached the client as a placeholder)"
            )
        elif restored:
            logger.debug(f"PII guard: {restored} surrogate(s) restored")
        return out


def _escaped(original: str) -> bytes:
    """JSON-escape a value for substitution inside a JSON string literal."""
    return json.dumps(original, ensure_ascii=False)[1:-1].encode("utf-8")


def restore_bytes(data: bytes, vault: PiiVault) -> bytes:
    """
    Restore a complete (non-streamed) body in one pass.

    Works on raw bytes so it applies to any body shape, including upstream
    error envelopes that quote the request back. Substituted values are
    JSON-escaped, since the surrogate sits inside a JSON string.
    """
    def repl(m):
        original = vault.original_for(m.group().decode("ascii"))
        return m.group() if original is None else _escaped(original)

    return TOKEN_RE_BYTES.sub(repl, data)


async def restore_stream(
    source: AsyncIterator[bytes],
    vault: PiiVault,
    sse: bool = True,
    restore_tool_args: bool | None = None,
) -> AsyncIterator[bytes]:
    """
    Wrap a byte stream, restoring surrogates as it passes through.

    Args:
        source: The upstream byte iterator.
        vault: The per-request surrogate vault.
        sse: True for ``text/event-stream``. When False the body is buffered
            and substituted in one pass — correct for a whole JSON response,
            which the client cannot use incrementally anyway.
        restore_tool_args: Restore surrogates inside tool-call arguments
            (``arguments`` / ``partial_json``) in addition to prose. Defaults
            to ``PII_RESTORE_TOOL_ARGS`` when not given explicitly, so
            production callers get the configured policy and tests can still
            pin a value directly.

    Fails open: an unexpected exception while restoring is logged once at
    ERROR level, and the rest of the stream (from the failing chunk onward)
    is passed through unmodified rather than propagating and killing the
    response mid-stream. A surrogate reaching the client is a privacy miss;
    a truncated response is worse.
    """
    if restore_tool_args is None:
        from kiro.config import PII_RESTORE_TOOL_ARGS

        restore_tool_args = PII_RESTORE_TOOL_ARGS

    if not sse:
        buf = bytearray()
        async for chunk in source:
            buf += chunk
        try:
            yield restore_bytes(bytes(buf), vault)
        except Exception as exc:
            logger.error(f"PII guard: restore_bytes failed, forwarding body unmodified: {exc}")
            yield bytes(buf)
        return

    restorer = SseRestorer(vault, restore_tool_args=restore_tool_args)
    broken = False
    try:
        async for chunk in source:
            if broken:
                yield chunk
                continue
            try:
                out = restorer.feed(chunk)
            except Exception as exc:
                logger.error(
                    "PII guard: SseRestorer.feed failed, passing the rest of "
                    f"the stream through unmodified: {exc}"
                )
                broken = True
                out = chunk
            if out:
                yield out
    finally:
        if not broken:
            try:
                tail = restorer.flush()
            except Exception as exc:
                logger.error(f"PII guard: SseRestorer.flush failed: {exc}")
                tail = b""
            if tail:
                yield tail
