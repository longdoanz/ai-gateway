import asyncio
from dataclasses import dataclass

from loguru import logger


@dataclass
class UsageEntry:
    key_id: int
    current_usage: int
    usage_limit: int
    is_active: bool


class UsageCache:
    def __init__(self):
        self._cache: dict[int, UsageEntry] = {}
        self._lock = asyncio.Lock()

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
        return self._cache.get(key_id)

    async def increment(self, key_id: int, amount: int = 1) -> None:
        async with self._lock:
            entry = self._cache.get(key_id)
            if entry:
                entry.current_usage += amount

    async def refresh_limits(self, updates: dict[int, tuple[int, int]]) -> None:
        async with self._lock:
            for key_id, (usage_limit, current_usage) in updates.items():
                entry = self._cache.get(key_id)
                if entry:
                    entry.usage_limit = usage_limit
                    entry.current_usage = current_usage

    def get_available_keys(self, exclude_key_id: int | None = None) -> list[int]:
        available = []
        for key_id, entry in self._cache.items():
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
