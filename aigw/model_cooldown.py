# -*- coding: utf-8 -*-
"""
Per-model cooldown for 9router multi-level override failover.

When an override target fails with a transient error (429, 5xx, connect /
timeout), it is put on cooldown with exponential backoff so later requests skip
straight to the next candidate instead of hitting the broken model again on
every call. A success clears the model's state.

Deterministic, payload-level errors (other 4xx) must NOT feed this cache:
resending the same payload to another model or later gives the same error, so
cooling the model down would only punish a healthy target.

State is in-process (one cache per worker) and keyed by the admin-configured
target model names, so it stays bounded.
"""

import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Callable, Dict, List, Optional, TypeVar

from loguru import logger

T = TypeVar("T")

# Statuses worth backing off from — the upstream may recover on its own.
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def is_transient_status(status_code: int) -> bool:
    """Return True when an upstream status is transient (cooldown-worthy).

    Args:
        status_code: HTTP status returned by the upstream.

    Returns:
        True for 408/425/429 and any 5xx.
    """
    return status_code in TRANSIENT_STATUSES or 500 <= status_code < 600


def parse_retry_after(value: Optional[str], now: Optional[float] = None) -> Optional[float]:
    """Parse a ``Retry-After`` header into seconds.

    Args:
        value: Header value — delta-seconds or an HTTP-date.
        now: Current epoch time (for the HTTP-date form); defaults to time.time().

    Returns:
        Non-negative seconds, or None when absent/unparseable.
    """
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    return max(0.0, dt.timestamp() - (time.time() if now is None else now))


@dataclass
class _State:
    failures: int
    until: float


class ModelCooldown:
    """Exponential-backoff cooldown tracker keyed by model name."""

    def __init__(
        self,
        base_seconds: float,
        max_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        Args:
            base_seconds: Cooldown after the first failure; doubles per
                consecutive failure. ``<= 0`` disables the cache.
            max_seconds: Upper bound for any single cooldown (also caps
                ``Retry-After``).
            clock: Monotonic time source (injectable for tests).
        """
        self.base = base_seconds
        self.max = max(max_seconds, base_seconds)
        self._clock = clock
        self._state: Dict[str, _State] = {}

    @property
    def enabled(self) -> bool:
        return self.base > 0

    def remaining(self, model: str) -> float:
        """Seconds left on the model's cooldown (0 when it is available)."""
        st = self._state.get(model)
        if st is None:
            return 0.0
        return max(0.0, st.until - self._clock())

    def record_failure(self, model: str, retry_after: Optional[float] = None) -> float:
        """Register a transient failure and start/extend the cooldown.

        Args:
            model: The failed target model.
            retry_after: Upstream ``Retry-After`` in seconds, if any — used
                instead of the computed backoff (capped at ``max``).

        Returns:
            The cooldown duration applied, in seconds.
        """
        if not self.enabled:
            return 0.0
        now = self._clock()
        st = self._state.get(model)
        # A failure long after the previous cooldown ended starts a new streak.
        if st is None or now - st.until > self.max:
            failures = 1
        else:
            failures = st.failures + 1
        if retry_after is not None:
            duration = min(retry_after, self.max)
        else:
            duration = min(self.base * (2 ** (failures - 1)), self.max)
        self._state[model] = _State(failures=failures, until=now + duration)
        logger.warning(
            f"9router override cooldown: {model!r} failed {failures}x in a row, "
            f"skipping it for {duration:.0f}s"
        )
        return duration

    def record_success(self, model: str) -> None:
        """Clear any cooldown state for the model."""
        if self._state.pop(model, None) is not None:
            logger.info(f"9router override cooldown: {model!r} recovered")

    def order(self, candidates: List[T], key: Callable[[T], Optional[str]] = lambda c: c) -> List[T]:
        """Drop candidates currently on cooldown, keeping the configured order.

        When every candidate is cooling down, the one whose cooldown ends
        soonest is returned alone as a probe, so the request is still served
        and a recovered model is detected.

        Args:
            candidates: Ordered failover candidates.
            key: Maps a candidate to its model name (None = never cooled).

        Returns:
            The candidates to actually try, in order (never empty unless the
            input is).
        """
        if not self.enabled or len(candidates) <= 1:
            return list(candidates)
        available = [c for c in candidates if key(c) is None or self.remaining(key(c)) == 0]
        if available:
            skipped = [key(c) for c in candidates if c not in available]
            if skipped:
                logger.info(f"9router override cooldown: skipping {skipped}")
            return available
        probe = min(candidates, key=lambda c: self.remaining(key(c)))
        logger.info(f"9router override cooldown: all candidates cooling down, probing {key(probe)!r}")
        return [probe]

    def clear(self) -> None:
        """Forget all cooldown state."""
        self._state.clear()
