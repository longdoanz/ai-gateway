import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from kiro.config import (
    DATABASE_URL,
    DB_POOL_SIZE,
    DB_MAX_OVERFLOW,
    DB_POOL_RECYCLE,
    DB_POOL_TIMEOUT,
)

logger = logging.getLogger(__name__)

# alembic.ini and the versions tree live at the repo root; resolve from this file
# so the path holds wherever the process is started from (uvicorn, container, cwd).
_REPO_ROOT = Path(__file__).resolve().parents[2]

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


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    # script_location in alembic.ini is %(here)s-relative, which resolves against
    # the ini's directory — pin it explicitly so a relocated ini still works.
    # sqlalchemy.url is deliberately left empty: alembic/env.py prefers
    # kiro.config.DATABASE_URL, which avoids round-tripping the secret (and any
    # '%' in a URL-encoded password) through config interpolation.
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    return cfg


def _upgrade_schema_sync() -> None:
    from alembic import command

    command.upgrade(_alembic_config(), "head")


def _head_revision() -> str | None:
    """Newest revision, used to name the recovery command for a legacy database."""
    try:
        from alembic.script import ScriptDirectory

        heads = ScriptDirectory.from_config(_alembic_config()).get_heads()
        return heads[0] if heads else None
    except Exception:
        return None


async def init_db():
    """Bring the schema up to date by running migrations. Never creates tables directly.

    This used to call ``Base.metadata.create_all``. Two problems with that:

    * It raced Alembic. In production the gateway started first and created any
      missing table, so the separate ``alembic upgrade head`` job then failed with
      ``DuplicateTableError`` and aborted the deploy.
    * It only ever ran ``CREATE TABLE``. A column added to a model was invisible to
      an existing database, so the ORM and the schema silently disagreed.

    Running the migrations instead makes Alembic the single source of schema truth,
    and is a no-op when the database is already at head.
    """
    if not DATABASE_URL:
        return
    try:
        await asyncio.to_thread(_upgrade_schema_sync)
    except Exception as exc:
        # A database left by the old create_all bootstrap has the tables but no
        # alembic_version row, so the first migration collides with them. It is
        # recoverable with a one-time stamp at *head* — the tables are already the
        # shape head describes, so stamping the baseline instead would only move the
        # collision to the next revision. Say so rather than just raising.
        if "already exists" in str(exc) and (head := _head_revision()):
            logger.error(
                "Schema upgrade failed: the tables exist but Alembic has no record of "
                "them (a database created by the old create_all startup). Adopt it once "
                "with `alembic stamp %s`, then restart.",
                head,
            )
        raise


async def close_db():
    if engine is not None:
        await engine.dispose()
