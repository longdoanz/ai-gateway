import asyncio

from loguru import logger

from kiro.db.engine import async_session_factory
from kiro.db.repositories import decrypt_api_key
from kiro.usage.usage_cache import usage_cache


class NoAvailableKeyError(Exception):
    pass


class FallbackRouter:
    def __init__(self):
        self._counter = 0
        self._lock = asyncio.Lock()
        self._sharing_enabled: bool = False

    def update_sharing_config(self, enabled: bool) -> None:
        self._sharing_enabled = enabled

    async def pre_check(self, current_key_id: int) -> tuple[int, str] | None:
        if not self._sharing_enabled:
            return None

        entry = usage_cache.get(current_key_id)
        if entry is None or entry.usage_limit <= 0:
            return None

        remaining_ratio = (entry.usage_limit - entry.current_usage) / entry.usage_limit
        if remaining_ratio >= 0.01:
            return None

        logger.info(f"Key {current_key_id} at {remaining_ratio:.1%} remaining, triggering fallback")
        return await self._pick_fallback_key(current_key_id)

    async def post_check(self, current_key_id: int) -> tuple[int, str] | None:
        if not self._sharing_enabled:
            return None
        logger.info(f"Key {current_key_id} got 429, triggering fallback")
        return await self._pick_fallback_key(current_key_id)

    async def _pick_fallback_key(self, exclude_key_id: int) -> tuple[int, str]:
        available = usage_cache.get_available_keys(exclude_key_id=exclude_key_id)
        if not available:
            raise NoAvailableKeyError("No available keys with remaining quota")

        async with self._lock:
            idx = self._counter % len(available)
            self._counter += 1

        picked_key_id = available[idx]

        if async_session_factory is None:
            raise NoAvailableKeyError("Database not configured")
        from kiro.db.models import ApiKey
        from sqlalchemy import select
        async with async_session_factory() as session:
            result = await session.execute(select(ApiKey.key_encrypted).where(ApiKey.id == picked_key_id))
            encrypted = result.scalar_one_or_none()
        if encrypted is None:
            raise NoAvailableKeyError(f"Key {picked_key_id} not found in DB")

        raw_key = decrypt_api_key(encrypted)
        logger.info(f"Fallback: switched from key {exclude_key_id} to key {picked_key_id}")
        return picked_key_id, raw_key


fallback_router = FallbackRouter()
