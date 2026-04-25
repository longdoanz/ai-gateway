import asyncio

from loguru import logger

from kiro.config import REGION, USAGE_SYNC_INTERVAL
from kiro.db.engine import async_session_factory
from kiro.db.models import ApiKey
from kiro.db.repositories import decrypt_api_key, upsert_usage_limits, update_api_key
from kiro.usage.usage_cache import usage_cache


async def sync_usage_limits() -> None:
    if async_session_factory is None:
        return

    from kiro.api_key_mode import get_usage_limits, build_api_key_headers
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.is_active == True))
        active_keys = list(result.scalars().all())

    logger.info(f"Sync worker: syncing usage limits for {len(active_keys)} active keys")
    cache_updates: dict[int, tuple[int, int]] = {}

    for key in active_keys:
        try:
            raw_key = decrypt_api_key(key.key_encrypted)
            data = await get_usage_limits(raw_key, resource_type="CREDIT")

            breakdown_list = data.get("usageBreakdownList", [])
            if not breakdown_list:
                continue

            credit_entry = None
            for entry in breakdown_list:
                if entry.get("resourceType") == "CREDIT":
                    credit_entry = entry
                    break
            if credit_entry is None:
                credit_entry = breakdown_list[0]

            usage_limit = int(credit_entry.get("usageLimit", 0))
            current_usage_precise = credit_entry.get("currentUsageWithPrecision")
            current_usage = int(current_usage_precise) if current_usage_precise is not None else int(credit_entry.get("currentUsage", 0))

            from datetime import datetime
            month = datetime.utcnow().strftime("%Y-%m")

            async with async_session_factory() as session:
                await upsert_usage_limits(session, key.id, month, usage_limit, current_usage)

            cache_updates[key.id] = (usage_limit, current_usage)

            # Update kiro_user_id mapping if available
            user_info = data.get("userInfo", {})
            kiro_user_id = user_info.get("userId")
            if kiro_user_id and kiro_user_id != key.kiro_user_id:
                async with async_session_factory() as session:
                    await update_api_key(session, key.id, kiro_user_id=kiro_user_id)

            logger.debug(f"Synced key {key.id}: usage={current_usage}/{usage_limit}")

        except Exception as e:
            logger.warning(f"Sync worker: failed to sync key {key.id}: {e}")
            continue

    if cache_updates:
        await usage_cache.refresh_limits(cache_updates)
        logger.info(f"Sync worker: refreshed cache for {len(cache_updates)} keys")


async def run_sync_loop() -> None:
    while True:
        try:
            await sync_usage_limits()
        except asyncio.CancelledError:
            logger.info("Sync worker: cancelled")
            break
        except Exception as e:
            logger.error(f"Sync worker: unexpected error: {e}")
        await asyncio.sleep(USAGE_SYNC_INTERVAL)
