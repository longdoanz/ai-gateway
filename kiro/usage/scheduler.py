import asyncio

from loguru import logger

from kiro.config import DATABASE_URL
from kiro.db.engine import async_session_factory, init_db, close_db
from kiro.db.repositories import create_user, get_user_by_username
from kiro.usage.usage_cache import usage_cache
from kiro.usage.sync_worker import run_sync_loop, run_monthly_sync_loop, run_daily_snapshot_loop
from kiro.usage.daily_buffer import daily_buffer, gateway_key_daily_buffer


_sync_task: asyncio.Task | None = None
_monthly_sync_task: asyncio.Task | None = None
_daily_snapshot_task: asyncio.Task | None = None


def is_db_configured() -> bool:
    from kiro.config import API_KEY_MODE
    return bool(DATABASE_URL) and API_KEY_MODE


async def startup() -> None:
    global _sync_task

    if not is_db_configured():
        logger.info("Usage management: Not in API Key mode or DATABASE_URL not set, skipping init")
        return

    # Validate required secrets
    from kiro.config import ENCRYPTION_KEY, JWT_SECRET
    if not ENCRYPTION_KEY:
        logger.error("Usage management: ENCRYPTION_KEY is required when DATABASE_URL is set")
        raise RuntimeError("ENCRYPTION_KEY is required")
    if not JWT_SECRET:
        logger.error("Usage management: JWT_SECRET is required when DATABASE_URL is set")
        raise RuntimeError("JWT_SECRET is required")

    # Validate Fernet key format
    try:
        from cryptography.fernet import Fernet
        Fernet(ENCRYPTION_KEY.encode())
    except Exception as e:
        logger.error(f"Usage management: ENCRYPTION_KEY is not a valid Fernet key: {e}")
        raise RuntimeError(f"Invalid ENCRYPTION_KEY: {e}")

    await init_db()
    logger.info("Usage management: database initialized")

    # Seed admin user if configured and not exists
    from kiro.config import ADMIN_USERNAME, ADMIN_PASSWORD
    if ADMIN_USERNAME and ADMIN_PASSWORD:
        async with async_session_factory() as session:
            existing = await get_user_by_username(session, ADMIN_USERNAME)
            if existing is None:
                await create_user(session, ADMIN_USERNAME, ADMIN_PASSWORD, role="admin")
                logger.info(f"Usage management: created initial admin user '{ADMIN_USERNAME}'")

    # Load usage cache
    async with async_session_factory() as session:
        await usage_cache.load_from_db(session)

    # Immediately sync all keys to get real credit values from Kiro API.
    # Runs in background so startup is not blocked.
    from kiro.usage.sync_worker import sync_all_active_keys
    asyncio.create_task(sync_all_active_keys())
    logger.info("Usage management: triggered immediate startup sync")

    # Load initial fallback config
    from kiro.usage.fallback import fallback_router
    from kiro.db.repositories import get_all_config
    async with async_session_factory() as session:
        config = await get_all_config(session)
    fallback_router.update_sharing_config(config.get("enable_usage_sharing", "false").lower() == "true")

    # Start sync worker
    _sync_task = asyncio.create_task(run_sync_loop())
    logger.info("Usage management: sync worker started")

    _monthly_sync_task = asyncio.create_task(run_monthly_sync_loop())
    logger.info("Usage management: monthly sync job scheduled")

    _daily_snapshot_task = asyncio.create_task(run_daily_snapshot_loop())
    logger.info("Usage management: daily credit snapshot job scheduled")

    daily_buffer.start()
    logger.info("Usage management: daily buffer started")

    gateway_key_daily_buffer.start()
    logger.info("Usage management: gateway key daily buffer started")


async def shutdown() -> None:
    global _sync_task, _monthly_sync_task, _daily_snapshot_task

    if not is_db_configured():
        return

    if _sync_task is not None:
        _sync_task.cancel()
        try:
            await _sync_task
        except asyncio.CancelledError:
            pass
        logger.info("Usage management: sync worker stopped")

    if _monthly_sync_task is not None:
        _monthly_sync_task.cancel()
        try:
            await _monthly_sync_task
        except asyncio.CancelledError:
            pass
        logger.info("Usage management: monthly sync job stopped")

    if _daily_snapshot_task is not None:
        _daily_snapshot_task.cancel()
        try:
            await _daily_snapshot_task
        except asyncio.CancelledError:
            pass
        logger.info("Usage management: daily snapshot job stopped")

    await daily_buffer.stop()
    logger.info("Usage management: daily buffer stopped")

    await gateway_key_daily_buffer.stop()
    logger.info("Usage management: gateway key daily buffer stopped")

    await close_db()
    logger.info("Usage management: database closed")
