from datetime import datetime, timezone

from loguru import logger

from kiro.db.engine import async_session_factory
from kiro.db.repositories import increment_usage
from kiro.usage.usage_cache import usage_cache
from kiro.usage.daily_buffer import daily_buffer


async def track_usage(key_id: int, credits_used: int | None = None) -> None:
    """Increment usage counter for a key. If credits_used is None, defaults to +1 as approximation.
    If credits_used is 0, skips DB write entirely.
    The sync worker periodically overwrites with real values from getUsageLimits API."""
    if credits_used is not None and credits_used == 0:
        return
    amount = credits_used if credits_used is not None and credits_used > 0 else 1
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")

    try:
        if async_session_factory is None:
            return
        async with async_session_factory() as session:
            await increment_usage(session, key_id, month, amount)
        await usage_cache.increment(key_id, amount)
        today = now.strftime("%Y-%m-%d")
        daily_buffer.record(key_id, today, amount)
        logger.debug(f"Tracked {amount} credits for key_id={key_id} month={month}")
    except Exception as e:
        logger.error(f"Failed to track usage for key_id={key_id}: {e}")


def extract_credits_from_response(response_data: dict | bytes | None) -> int | None:
    if response_data is None:
        return None
    if isinstance(response_data, bytes):
        try:
            import json
            response_data = json.loads(response_data)
        except Exception:
            return None
    if isinstance(response_data, dict):
        breakdown = response_data.get("usageBreakdownList") or response_data.get("usageBreakdown") or []
        if isinstance(breakdown, list):
            for item in breakdown:
                if isinstance(item, dict) and "currentUsage" in item:
                    return int(item["currentUsage"])
        credits = response_data.get("creditsUsed") or response_data.get("credits_used")
        if credits is not None:
            return int(credits)
    return None
