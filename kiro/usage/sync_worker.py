import asyncio
import random
import time
from datetime import datetime, timedelta, timezone

from loguru import logger

from kiro.db.engine import async_session_factory
from kiro.db.models import ApiKey, KeyUsage
from kiro.db.repositories import decrypt_api_key, merge_duplicate_keys_for_user, get_all_config, upsert_kiro_user_mappings, upsert_usage_limits, upsert_daily_credit_snapshot, update_api_key
from kiro.usage.usage_cache import usage_cache

_SYNC_DELAY_MIN = 300   # 5 minutes
_SYNC_DELAY_MAX = 600   # 10 minutes
_LOOP_INTERVAL = 60     # poll interval

# key_id -> monotonic time when sync should fire
_pending_syncs: dict[int, float] = {}


def record_activity(key_id: int) -> None:
    """Schedule a usage-limit sync for key_id 5-10 minutes from now.
    If already scheduled, does not reset the timer."""
    if key_id not in _pending_syncs:
        delay = random.uniform(_SYNC_DELAY_MIN, _SYNC_DELAY_MAX)
        _pending_syncs[key_id] = time.monotonic() + delay
        logger.debug(f"Sync worker: scheduled sync for key {key_id} in {delay:.0f}s")


async def sync_usage_limits(key_ids: list[int]) -> None:
    if async_session_factory is None:
        return

    from kiro.api_key_mode import get_usage_limits
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.id.in_(key_ids), ApiKey.is_active == True)
        )
        keys = list(result.scalars().all())

    if not keys:
        return

    logger.info(f"Sync worker: syncing usage limits for {len(keys)} keys")
    cache_updates: dict[int, tuple[int, int]] = {}
    deactivated_this_cycle: set[int] = set()

    async with async_session_factory() as session:
        for key in keys:
            if key.id in deactivated_this_cycle:
                logger.debug(f"Sync worker: skipping key {key.id} (deactivated earlier this cycle)")
                continue
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

                raw_reset = credit_entry.get("nextDateReset") or data.get("nextDateReset")
                next_reset_at: float | None = float(raw_reset) if raw_reset is not None else None

                from datetime import datetime, timezone
                month = datetime.now(timezone.utc).strftime("%Y-%m")

                await upsert_usage_limits(session, key.id, month, usage_limit, current_usage)

                cache_updates[key.id] = (usage_limit, current_usage, next_reset_at)

                user_info = data.get("userInfo", {})
                kiro_user_id = user_info.get("userId")
                if kiro_user_id and kiro_user_id != key.kiro_user_id:
                    await upsert_kiro_user_mappings(session, [{"kiro_user_id": kiro_user_id}])
                    await update_api_key(session, key.id, kiro_user_id=kiro_user_id)

                if kiro_user_id:
                    survivor_id, _ = await merge_duplicate_keys_for_user(session, key.id, kiro_user_id)
                    if survivor_id != key.id:
                        logger.info(f"Sync worker: updated preferred key for user {kiro_user_id}, survivor={survivor_id}")

                logger.debug(f"Synced key {key.id}: usage={current_usage}/{usage_limit} next_reset_at={next_reset_at}")

            except Exception as e:
                from fastapi import HTTPException as FastAPIHTTPException
                if isinstance(e, FastAPIHTTPException) and e.status_code == 401:
                    logger.warning(f"Sync worker: key {key.id} returned 401/403 — deactivating")
                    await update_api_key(session, key.id, is_active=False)
                    usage_cache.set_key_active(key.id, False)
                else:
                    logger.warning(f"Sync worker: failed to sync key {key.id}: {e}")
                continue

    if cache_updates:
        await usage_cache.refresh_limits(cache_updates)
        logger.info(f"Sync worker: refreshed cache for {len(cache_updates)} keys")

    await _snapshot_daily_credits()


async def _snapshot_daily_credits() -> None:
    """Snapshot current_usage per kiro_user for today (MAX per user across keys)."""
    if async_session_factory is None:
        return
    from sqlalchemy import func, select

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")

    async with async_session_factory() as session:
        result = await session.execute(
            select(
                ApiKey.kiro_user_id,
                func.max(KeyUsage.current_usage).label("current_usage"),
            )
            .join(ApiKey, ApiKey.id == KeyUsage.key_id)
            .where(KeyUsage.month == current_month, ApiKey.kiro_user_id.isnot(None))
            .group_by(ApiKey.kiro_user_id)
        )
        rows = result.all()

    if not rows:
        return

    async with async_session_factory() as session:
        for row in rows:
            await upsert_daily_credit_snapshot(session, row.kiro_user_id, today, int(row.current_usage))


async def sync_all_active_keys() -> None:
    """Fetch all active key IDs from DB and sync usage limits for each."""
    if async_session_factory is None:
        return
    from sqlalchemy import select
    async with async_session_factory() as session:
        result = await session.execute(
            select(ApiKey.id).where(ApiKey.is_active == True)
        )
        key_ids = [row[0] for row in result.all()]
    if not key_ids:
        logger.info("Monthly sync: no active keys found")
        return
    logger.info(f"Monthly sync: syncing {len(key_ids)} active keys")
    await sync_usage_limits(key_ids)


async def run_monthly_sync_loop() -> None:
    """Fire sync_all_active_keys at 00:30 UTC on the 1st of each month (= 07:30 UTC+7)."""
    while True:
        now = datetime.now(timezone.utc)
        if now.month == 12:
            next_run = datetime(now.year + 1, 1, 1, 0, 30, 0, tzinfo=timezone.utc)
        else:
            next_run = datetime(now.year, now.month + 1, 1, 0, 30, 0, tzinfo=timezone.utc)
        sleep_secs = (next_run - now).total_seconds()
        logger.info(f"Monthly sync: next run at {next_run.isoformat()} (in {sleep_secs:.0f}s)")
        try:
            await asyncio.sleep(sleep_secs)
        except asyncio.CancelledError:
            logger.info("Monthly sync: cancelled")
            break
        try:
            await sync_all_active_keys()
        except Exception as e:
            logger.error(f"Monthly sync: unexpected error: {e}")


async def run_daily_snapshot_loop() -> None:
    """Snapshot credit usage at 23:55 UTC daily."""
    while True:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=23, minute=55, second=0, microsecond=0)
        if now >= target:
            target = target + timedelta(days=1)
        sleep_secs = (target - now).total_seconds()
        logger.info(f"Daily snapshot: next run at {target.isoformat()} (in {sleep_secs:.0f}s)")
        try:
            await asyncio.sleep(sleep_secs)
        except asyncio.CancelledError:
            logger.info("Daily snapshot: cancelled")
            break
        try:
            await _snapshot_daily_credits()
            logger.info("Daily snapshot: completed")
        except Exception as e:
            logger.error(f"Daily snapshot: unexpected error: {e}")


async def run_sync_loop() -> None:
    while True:
        try:
            now = time.monotonic()
            due = [kid for kid, fire_at in list(_pending_syncs.items()) if now >= fire_at]
            for kid in due:
                _pending_syncs.pop(kid, None)
            if due:
                await sync_usage_limits(due)
                from kiro.usage.fallback import fallback_router
                async with async_session_factory() as session:
                    config = await get_all_config(session)
                fallback_router.update_sharing_config(config.get("enable_usage_sharing", "false").lower() == "true")

        except asyncio.CancelledError:
            logger.info("Sync worker: cancelled")
            break
        except Exception as e:
            logger.error(f"Sync worker: unexpected error: {e}")
        await asyncio.sleep(_LOOP_INTERVAL)
