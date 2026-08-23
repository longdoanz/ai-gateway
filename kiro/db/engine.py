import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from kiro.config import (
    DATABASE_URL,
    DB_POOL_SIZE,
    DB_MAX_OVERFLOW,
    DB_POOL_RECYCLE,
    DB_POOL_TIMEOUT,
)

logger = logging.getLogger(__name__)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=DB_POOL_RECYCLE,
    pool_timeout=DB_POOL_TIMEOUT,
) if DATABASE_URL else None

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False) if engine else None


async def get_session():
    if async_session_factory is None:
        raise RuntimeError("Database not configured (DATABASE_URL is empty)")
    async with async_session_factory() as session:
        try:
            yield session
        except asyncio.CancelledError:
            logger.debug("Request cancelled, closing DB session gracefully")
            raise


async def init_db():
    if engine is None:
        return
    from kiro.db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    if engine is not None:
        await engine.dispose()
