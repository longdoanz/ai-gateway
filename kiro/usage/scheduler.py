import asyncio

from loguru import logger

from kiro.config import DATABASE_URL
from kiro.db.engine import async_session_factory, init_db, close_db
from kiro.db.repositories import create_user, get_user_by_username
from kiro.usage.usage_cache import usage_cache
from kiro.usage.sync_worker import run_sync_loop


_sync_task: asyncio.Task | None = None


def is_db_configured() -> bool:
    return bool(DATABASE_URL)


async def startup() -> None:
    global _sync_task

    if not is_db_configured():
        logger.info("Usage management: DATABASE_URL not set, skipping init")
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

    # Start sync worker
    _sync_task = asyncio.create_task(run_sync_loop())
    logger.info("Usage management: sync worker started")


async def shutdown() -> None:
    global _sync_task

    if not is_db_configured():
        return

    if _sync_task is not None:
        _sync_task.cancel()
        try:
            await _sync_task
        except asyncio.CancelledError:
            pass
        logger.info("Usage management: sync worker stopped")

    await close_db()
    logger.info("Usage management: database closed")
