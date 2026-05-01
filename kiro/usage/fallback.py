import asyncio

from loguru import logger

from kiro.usage.usage_cache import usage_cache, sticky_binder


class NoAvailableKeyError(Exception):
    pass


class FallbackRouter:
    def __init__(self):
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
        # 429 means bound key is rate-limited, force re-bind
        sticky_binder.invalidate(current_key_id)
        return await self._pick_fallback_key(current_key_id)

    async def _pick_fallback_key(self, exclude_key_id: int) -> tuple[int, str]:
        available = usage_cache.get_available_keys(exclude_key_id=exclude_key_id)
        if not available:
            raise NoAvailableKeyError("No available keys with remaining quota")

        picked_key_id, raw_key = await sticky_binder.pick_and_decrypt(exclude_key_id, available)
        logger.info(f"Fallback: switched from key {exclude_key_id} to key {picked_key_id}")
        return picked_key_id, raw_key


fallback_router = FallbackRouter()
