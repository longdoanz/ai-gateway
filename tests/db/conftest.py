# -*- coding: utf-8 -*-

"""
Real-Postgres fixtures for tests that depend on Postgres semantics (ON
CONFLICT, NULLS NOT DISTINCT, migrations) which mocks cannot exercise.

The server is a throwaway ``postgres:18`` container (same major as prod)
whose data directory is a tmpfs, so it lives entirely in RAM and starts in a
couple of seconds. Each test gets its own freshly created database.

Set ``TEST_PG_ADMIN_URL`` (an asyncpg URL to any database on a server you own,
e.g. ``postgresql+asyncpg://postgres:pw@localhost:5432/postgres``) to use an
existing server instead. Without either Docker or that variable, every test
in this directory is skipped.
"""

import asyncio
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
_IMAGE = os.getenv("TEST_PG_IMAGE", "postgres:18")


def _start_container() -> tuple[str, str]:
    """Start a tmpfs-backed Postgres container; return (container id, admin URL)."""
    cid = subprocess.run(
        [
            "docker", "run", "-d", "--rm",
            "--tmpfs", "/var/lib/postgresql:rw",
            "-e", "POSTGRES_PASSWORD=test",
            "-p", "127.0.0.1::5432",
            _IMAGE,
            # Durability is pointless for a RAM-backed throwaway server.
            "-c", "fsync=off", "-c", "synchronous_commit=off", "-c", "full_page_writes=off",
        ],
        capture_output=True, text=True, check=True, timeout=120,
    ).stdout.strip()
    port = subprocess.run(
        ["docker", "port", cid, "5432/tcp"], capture_output=True, text=True, check=True
    ).stdout.strip().splitlines()[0].rsplit(":", 1)[1]
    return cid, f"postgresql+asyncpg://postgres:test@127.0.0.1:{port}/postgres"


async def _wait_ready(admin_url: str, timeout: float = 60.0) -> None:
    dsn = admin_url.replace("+asyncpg", "")
    deadline = time.monotonic() + timeout
    while True:
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            return
        except (OSError, asyncpg.PostgresError):
            # The entrypoint restarts the server once after initdb, so a first
            # successful connect can still race a shutdown — just retry.
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(0.3)


@pytest.fixture(scope="session")
def pg_admin_url():
    """URL of a database on a disposable Postgres server (session-wide)."""
    url = os.getenv("TEST_PG_ADMIN_URL")
    if url:
        yield url
        return
    if shutil.which("docker") is None:
        pytest.skip("Postgres tests need Docker or TEST_PG_ADMIN_URL")
    try:
        cid, url = _start_container()
    except (subprocess.SubprocessError, OSError) as exc:
        pytest.skip(f"Could not start a Postgres container: {exc}")
    try:
        asyncio.run(_wait_ready(url))
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True)


@pytest.fixture
def fresh_db_url(pg_admin_url):
    """Create an empty database for one test and drop it afterwards."""
    name = f"t_{uuid.uuid4().hex[:12]}"
    admin_dsn = pg_admin_url.replace("+asyncpg", "")

    async def _exec(sql: str) -> None:
        conn = await asyncpg.connect(admin_dsn)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(_exec(f'CREATE DATABASE "{name}"'))
    yield pg_admin_url.rsplit("/", 1)[0] + f"/{name}"
    asyncio.run(_exec(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def alembic_upgrade(db_url: str, revision: str = "head") -> None:
    """Run ``alembic upgrade`` against ``db_url`` in a subprocess.

    A subprocess keeps alembic's own ``asyncio.run`` off the test's loop and
    makes aigw.config read this URL instead of whatever the repo .env holds
    (load_dotenv never overrides a variable that is already set).

    Args:
        db_url: asyncpg database URL to migrate.
        revision: Target revision (default ``head``).
    """
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:]


@pytest.fixture
def migrated_db_url(fresh_db_url):
    """A fresh database migrated to the latest revision."""
    alembic_upgrade(fresh_db_url)
    return fresh_db_url


@pytest_asyncio.fixture
async def session_factory(migrated_db_url):
    """async_sessionmaker bound to a migrated test database."""
    engine = create_async_engine(migrated_db_url)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()
