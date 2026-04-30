import asyncio
import time
from dataclasses import dataclass

from loguru import logger


@dataclass
class UsageEntry:
    key_id: int
    current_usage: int
    usage_limit: int
    is_active: bool
    next_reset_at: float | None = None


class UsageCache:
    def __init__(self):
        self._cache: dict[int, UsageEntry] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _maybe_reset(entry: "UsageEntry") -> None:
        """Reset current_usage to 0 if the billing period has rolled over."""
        if entry.next_reset_at is not None and time.time() >= entry.next_reset_at:
            logger.info(f"UsageCache: resetting usage for key {entry.key_id} (next_reset_at passed)")
            entry.current_usage = 0
            entry.next_reset_at = None

    async def load_from_db(self, session) -> None:
        from kiro.db.models import ApiKey, KeyUsage
        from sqlalchemy import select
        from datetime import datetime, timezone

        current_month = datetime.now(timezone.utc).strftime("%Y-%m")

        keys_result = await session.execute(select(ApiKey))
        keys = {k.id: k for k in keys_result.scalars().all()}

        usage_result = await session.execute(select(KeyUsage).where(KeyUsage.month == current_month))
        usage_map = {u.key_id: u for u in usage_result.scalars().all()}

        async with self._lock:
            self._cache.clear()
            for key_id, key in keys.items():
                usage = usage_map.get(key_id)
                self._cache[key_id] = UsageEntry(
                    key_id=key_id,
                    current_usage=usage.current_usage if usage else 0,
                    usage_limit=usage.usage_limit if usage else 0,
                    is_active=key.is_active,
                )
        logger.info(f"UsageCache loaded: {len(self._cache)} keys")

    def get(self, key_id: int) -> UsageEntry | None:
        entry = self._cache.get(key_id)
        if entry:
            self._maybe_reset(entry)
        return entry

    async def increment(self, key_id: int, amount: int = 1) -> None:
        async with self._lock:
            entry = self._cache.get(key_id)
            if entry:
                self._maybe_reset(entry)
                entry.current_usage += amount

    async def refresh_limits(self, updates: dict[int, tuple[int, int, float | None]]) -> None:
        async with self._lock:
            for key_id, (usage_limit, current_usage, next_reset_at) in updates.items():
                entry = self._cache.get(key_id)
                if entry:
                    entry.usage_limit = usage_limit
                    entry.current_usage = current_usage
                    if next_reset_at is not None:
                        entry.next_reset_at = next_reset_at

    def get_available_keys(self, exclude_key_id: int | None = None) -> list[int]:
        available = []
        for key_id, entry in self._cache.items():
            self._maybe_reset(entry)
            if not entry.is_active:
                continue
            if key_id == exclude_key_id:
                continue
            if entry.usage_limit <= 0:
                continue
            remaining_ratio = (entry.usage_limit - entry.current_usage) / entry.usage_limit
            if remaining_ratio > 0.01:
                available.append(key_id)
        return available

    def set_key_active(self, key_id: int, is_active: bool) -> None:
        entry = self._cache.get(key_id)
        if entry:
            entry.is_active = is_active


usage_cache = UsageCache()
