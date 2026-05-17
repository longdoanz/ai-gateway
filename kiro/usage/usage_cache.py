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
    is_system: bool = False
    use_proxy: bool = False
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
                    is_system=key.is_system,
                    use_proxy=key.use_proxy,
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

    def remove_key(self, key_id: int) -> None:
        self._cache.pop(key_id, None)


usage_cache = UsageCache()


_STICKY_BIND_TTL = 900  # 15 minutes


class StickyKeyBinder:
    """Picks a pool key with sticky binding to preserve upstream prompt cache.

    Each binding_id (gateway_key.id or original_key_id) is bound to one pool
    key for 15 minutes. Re-binds when TTL expires or the bound key is no
    longer available.
    """

    def __init__(self):
        self._bindings: dict[int, tuple[int, float]] = {}

    def pick(self, binding_id: int, available: list[int]) -> int:
        now = time.time()
        binding = self._bindings.get(binding_id)
        if binding:
            bound_key_id, bound_until = binding
            if now < bound_until and bound_key_id in available:
                return bound_key_id

        best = max(
            available,
            key=lambda kid: (
                (usage_cache.get(kid).usage_limit - usage_cache.get(kid).current_usage)
                if usage_cache.get(kid) else 0
            ),
        )
        self._bindings[binding_id] = (best, now + _STICKY_BIND_TTL)
        return best

    def invalidate(self, binding_id: int) -> None:
        self._bindings.pop(binding_id, None)

    async def pick_and_decrypt(self, binding_id: int, available: list[int]) -> tuple[int, str]:
        """Pick a sticky key and decrypt it. Returns (key_id, raw_key)."""
        from kiro.db.engine import async_session_factory
        from kiro.db.repositories import decrypt_api_key
        from kiro.db.models import ApiKey
        from sqlalchemy import select

        picked_key_id = self.pick(binding_id, available)

        async with async_session_factory() as session:
            result = await session.execute(
                select(ApiKey.key_encrypted).where(ApiKey.id == picked_key_id)
            )
            encrypted = result.scalar_one_or_none()
        if encrypted is None:
            self.invalidate(binding_id)
            raise KeyError(f"Key {picked_key_id} not found in DB")

        return picked_key_id, decrypt_api_key(encrypted)


sticky_binder = StickyKeyBinder()
