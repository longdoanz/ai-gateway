# -*- coding: utf-8 -*-

"""
Per-request surrogate vault.

Lifetime is one call to ``forward_to_nine_router``: the request is tokenized
on the way up and the response is restored on the way down inside the same
handler, so nothing needs to persist between requests and there is no shared
state to synchronise across replicas. The next turn arrives with the restored
(original) text and is tokenized afresh.

Tokens are stable per *value*, not per occurrence: the same email appearing
three times yields ``<<EMAIL_1>>`` three times, so the model can still tell
the three mentions are the same person. Presidio's ``encrypt`` operator
cannot do this — it uses a fresh IV per call, so identical inputs produce
different ciphertext.
"""

import re

# Chosen to be (a) vanishingly rare in real prompts, (b) plain ASCII so it
# survives any tokenizer intact, (c) self-delimiting, unlike base64 ciphertext
# whose trailing "=" padding has no boundary in free text.
TOKEN_RE = re.compile(r"<<([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)_(\d+)>>")
TOKEN_RE_BYTES = re.compile(rb"<<([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)_(\d+)>>")


class PiiVault:
    """Bidirectional map between original PII values and their surrogates."""

    __slots__ = ("_to_token", "_to_original", "_counts", "_max_token_len")

    def __init__(self) -> None:
        self._to_token: dict[tuple[str, str], str] = {}
        self._to_original: dict[str, str] = {}
        self._counts: dict[str, int] = {}
        self._max_token_len = 0

    def token_for(self, entity_type: str, original: str) -> str:
        """Return the surrogate for ``original``, minting a stable one on first sight."""
        key = (entity_type, original)
        token = self._to_token.get(key)
        if token is None:
            n = self._counts[entity_type] = self._counts.get(entity_type, 0) + 1
            token = f"<<{entity_type}_{n}>>"
            self._to_token[key] = token
            self._to_original[token] = original
            if len(token) > self._max_token_len:
                self._max_token_len = len(token)
        return token

    def original_for(self, token: str) -> str | None:
        return self._to_original.get(token)

    @property
    def max_token_len(self) -> int:
        """Longest surrogate minted — the carry-buffer bound for streaming."""
        return self._max_token_len

    def __len__(self) -> int:
        return len(self._to_original)

    def __bool__(self) -> bool:
        return bool(self._to_original)

    def summary(self) -> dict[str, int]:
        """Counts per entity type, for logging. Never contains the values."""
        return dict(self._counts)
