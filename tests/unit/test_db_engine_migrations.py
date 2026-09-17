# -*- coding: utf-8 -*-

"""
Unit tests for kiro.db.engine.init_db schema bootstrap.

init_db used to call Base.metadata.create_all, which raced the production
`alembic upgrade head` service: whichever ran first created the tables, and the
second failed with DuplicateTableError, aborting the deploy. It now runs the
migrations instead, making Alembic the single source of schema truth.

Covers:
- init_db delegates to `alembic upgrade head` rather than creating tables.
- A failed upgrade that looks like a pre-existing table (a database left by the
  old create_all bootstrap) logs the one-time `alembic stamp <head>` recovery and
  re-raises. The stamp target must be head, not the baseline: a baseline stamp
  only moves the collision to the next revision, because such a database already
  has every table head describes.
- alembic/env.py must not let fileConfig disable existing loggers, or that
  recovery message is silently dropped in production.
"""

import ast
import asyncio
import importlib
import logging

import pytest

# `import kiro.db.engine as x` binds the AsyncEngine that kiro/db/__init__.py
# re-exports, not the module. import_module gives back the module itself.
db_engine = importlib.import_module("kiro.db.engine")


@pytest.fixture
def wired(monkeypatch):
    """Point init_db at a real alembic config but a stub `upgrade`."""

    def wire(upgrade):
        import alembic.command

        monkeypatch.setattr(db_engine, "DATABASE_URL", "postgresql+asyncpg://u:p@localhost/x")
        monkeypatch.setattr(alembic.command, "upgrade", upgrade)

    return wire


def run(coro):
    """Run a coroutine without depending on the asyncio plugin's mode."""
    return asyncio.new_event_loop().run_until_complete(coro)


class TestInitDbRunsMigrations:
    def test_upgrades_to_head(self, wired):
        calls = {}
        wired(lambda cfg, rev: calls.update(rev=rev))

        run(db_engine.init_db())

        assert calls.get("rev") == "head"

    def test_never_calls_create_all(self, wired, monkeypatch):
        """The regression: create_all must not run at startup any more."""
        wired(lambda cfg, rev: None)

        from kiro.db import models

        def boom(*a, **kw):
            raise AssertionError("init_db must not call create_all")

        monkeypatch.setattr(models.Base.metadata, "create_all", boom, raising=False)

        run(db_engine.init_db())  # would raise if create_all were still wired in

    def test_no_database_configured_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(db_engine, "DATABASE_URL", "")
        run(db_engine.init_db())  # must not raise


class TestLegacyDatabaseRecoveryHint:
    def test_logs_stamp_head_then_reraises(self, wired, monkeypatch, caplog):
        head = db_engine._head_revision()
        assert head, "a head revision must exist"

        def fail(cfg, rev):
            raise RuntimeError('relation "kiro_user_mappings" already exists')

        wired(fail)

        with caplog.at_level(logging.ERROR, logger="kiro.db.engine"):
            with pytest.raises(RuntimeError):
                run(db_engine.init_db())

        assert f"alembic stamp {head}" in caplog.text

    def test_unrelated_failure_gets_no_stamp_hint(self, wired, caplog):
        """Only the already-exists case is a legacy bootstrap; don't mislabel the rest."""

        def fail(cfg, rev):
            raise RuntimeError("connection refused")

        wired(fail)

        with caplog.at_level(logging.ERROR, logger="kiro.db.engine"):
            with pytest.raises(RuntimeError):
                run(db_engine.init_db())

        assert "alembic stamp" not in caplog.text


class TestAlembicConfig:
    def test_config_resolves_script_location(self):
        cfg = db_engine._alembic_config()
        assert cfg.get_main_option("script_location") == str(db_engine._REPO_ROOT / "alembic")

    def test_head_revision_matches_the_script_directory(self):
        from alembic.script import ScriptDirectory

        heads = ScriptDirectory.from_config(db_engine._alembic_config()).get_heads()
        assert db_engine._head_revision() == heads[0]

    def test_head_revision_returns_none_instead_of_raising(self, monkeypatch):
        def boom():
            raise ValueError("bad config")

        monkeypatch.setattr(db_engine, "_alembic_config", boom)
        assert db_engine._head_revision() is None


class TestAlembicLoggingConfig:
    def test_fileconfig_keeps_existing_loggers_alive(self):
        """disable_existing_loggers=True would mute the recovery hint in production."""
        env_py = db_engine._REPO_ROOT / "alembic" / "env.py"
        tree = ast.parse(env_py.read_text())

        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "fileConfig"
        ]
        assert calls, "no fileConfig call found in alembic/env.py"

        for node in calls:
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            assert "disable_existing_loggers" in kwargs, (
                "fileConfig must pass disable_existing_loggers=False; the default "
                "(True) switches off the app's loggers and swallows init_db's "
                "legacy-database recovery message"
            )
            assert isinstance(kwargs["disable_existing_loggers"], ast.Constant)
            assert kwargs["disable_existing_loggers"].value is False
