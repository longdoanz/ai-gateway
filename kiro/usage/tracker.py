from datetime import datetime, timezone

from loguru import logger

from kiro.db.engine import async_session_factory
from kiro.db.repositories import get_canonical_usage_key_id, increment_usage
from kiro.usage.usage_cache import usage_cache
from kiro.usage.daily_buffer import daily_buffer


async def track_usage(key_id: int, input_tokens: int = 0, output_tokens: int = 0, model: str = "unknown") -> int | None:
    """Record token usage for a key. KeyUsage.current_usage is a rough request counter
    between syncs; the sync worker overwrites it with real credit values from Kiro API."""
    total = input_tokens + output_tokens
    if total == 0:
        logger.debug(f"track_usage: skipping zero tokens for key_id={key_id}")
        return None
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")

    logger.info(f"track_usage: model={model} input_tokens={input_tokens}, output_tokens={output_tokens}, key_id={key_id}")

    try:
        if async_session_factory is None:
            return None
        async with async_session_factory() as session:
            canonical_key_id = await get_canonical_usage_key_id(session, key_id)
            await increment_usage(session, canonical_key_id, month, 1)
        await usage_cache.increment(canonical_key_id, 1)
        today = now.strftime("%Y-%m-%d")
        daily_buffer.record(canonical_key_id, today, input_tokens, output_tokens, model=model)
        logger.info(f"Tracked {input_tokens}in/{output_tokens}out tokens model={model} for key_id={canonical_key_id} date={today}")
        return canonical_key_id
    except Exception as e:
        logger.error(f"Failed to track usage for key_id={key_id}: {e}")
        return None
