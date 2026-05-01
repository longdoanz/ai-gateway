"""
DB-based model override for Kiro Gateway.

Reads `enable_model_override` and `enforced_global_model` from the
system_config table with a short TTL cache, and applies the override
to incoming request objects before they are converted to Kiro payloads.
"""

import asyncio
import time
from typing import Any, Tuple

from loguru import logger

_CACHE_TTL = 30  # seconds
_override_cache: Tuple[bool, str, float] | None = None
_override_cache_lock = asyncio.Lock()


async def get_model_override() -> Tuple[bool, str]:
    global _override_cache

    now = time.time()
    if _override_cache is not None and now - _override_cache[2] < _CACHE_TTL:
        return _override_cache[0], _override_cache[1]

    async with _override_cache_lock:
        if _override_cache is not None and now - _override_cache[2] < _CACHE_TTL:
            return _override_cache[0], _override_cache[1]

        enabled, model = await _fetch_override_config()
        _override_cache = (enabled, model, time.time())
        return enabled, model


async def _fetch_override_config() -> Tuple[bool, str]:
    from kiro.config import ENABLE_MODEL_OVERRIDE, ENFORCED_GLOBAL_MODEL, API_KEY_MODE
    try:
        from kiro.db.engine import async_session_factory
        if async_session_factory is None:
            if API_KEY_MODE:
                return False, "auto"
            return ENABLE_MODEL_OVERRIDE, ENFORCED_GLOBAL_MODEL or "auto"

        from kiro.db.repositories import get_config
        async with async_session_factory() as session:
            enabled_raw = await get_config(session, "enable_model_override")
            model_raw = await get_config(session, "enforced_global_model")

        enabled = (enabled_raw or "false").lower() == "true"
        model = model_raw or "auto"
        return enabled, model
    except Exception as e:
        logger.warning(f"Failed to read model override config: {e}")
        if not API_KEY_MODE:
            return ENABLE_MODEL_OVERRIDE, ENFORCED_GLOBAL_MODEL or "auto"
        return False, "auto"


async def apply_model_override(request_data: Any) -> None:
    enabled, enforced_model = await get_model_override()
    if not enabled:
        return

    original = request_data.model
    if original != enforced_model:
        logger.debug(f"Model override: {original} -> {enforced_model}")
    request_data.model = enforced_model


def invalidate_cache() -> None:
    global _override_cache
    _override_cache = None
