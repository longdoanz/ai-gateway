# -*- coding: utf-8 -*-

"""Usage tracking against a real Postgres: upsert convergence, cache tokens, migrations."""

import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from aigw.db.models import GatewayKey, GatewayKeyDailyUsage, GatewayKeyUsage, User
from aigw.db.repositories import increment_gateway_key_daily_usage, increment_gateway_key_usage
from tests.db.conftest import alembic_upgrade


async def _make_gateway_key(session, username: str = "alice") -> int:
    user = User(username=username, password_hash="x")
    session.add(user)
    await session.flush()
    gk = GatewayKey(user_id=user.id, key_hash=username.ljust(64, "0"), key_prefix="iziaigw_", key_suffix="abcd")
    session.add(gk)
    await session.commit()
    return gk.id


class TestSchema:
    @pytest.mark.asyncio
    async def test_head_has_nulls_not_distinct_and_bigint_tokens(self, session_factory):
        async with session_factory() as s:
            defs = dict((await s.execute(text(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname LIKE 'uq_gw_%'"
            ))).all())
            types = dict((await s.execute(text(
                "SELECT table_name || '.' || column_name, data_type FROM information_schema.columns "
                "WHERE table_name IN ('gateway_key_daily_usage', 'service_account_daily_usage') "
                "AND column_name LIKE '%tokens'"
            ))).all())

        assert all("NULLS NOT DISTINCT" in d for d in defs.values()) and len(defs) == 2
        assert set(types.values()) == {"bigint"} and len(types) == 8


class TestUpsertConverges:
    @pytest.mark.asyncio
    async def test_monthly_usage_with_null_key_id_is_one_row(self, session_factory):
        async with session_factory() as s:
            gk_id = await _make_gateway_key(s)
            for _ in range(3):
                await increment_gateway_key_usage(s, gk_id, "2026-10", 1, key_id=None)
            rows = (await s.execute(select(GatewayKeyUsage))).scalars().all()

        assert [(r.gateway_key_id, r.current_usage, r.key_id) for r in rows] == [(gk_id, 3, None)]

    @pytest.mark.asyncio
    async def test_daily_usage_sums_tokens_and_cache_in_one_row(self, session_factory):
        async with session_factory() as s:
            gk_id = await _make_gateway_key(s)
            await increment_gateway_key_daily_usage(
                s, gk_id, "2026-10-03", 100_000, 50, model="m", cache_read_tokens=90_000, cache_creation_tokens=500
            )
            await increment_gateway_key_daily_usage(
                s, gk_id, "2026-10-03", 3_000_000_000, 70, model="m", cache_read_tokens=2_999_000_000
            )
            rows = (await s.execute(select(GatewayKeyDailyUsage))).scalars().all()

        assert len(rows) == 1
        r = rows[0]
        # 3e9 also proves the columns are BIGINT (int32 would overflow).
        assert (r.input_tokens, r.output_tokens) == (3_000_100_000, 120)
        assert (r.cache_read_tokens, r.cache_creation_tokens) == (2_999_090_000, 500)

    @pytest.mark.asyncio
    async def test_callback_to_buffer_to_db(self, session_factory):
        """The real 9router usage callback, through the daily buffer, into Postgres."""
        from aigw.api_key_mode import _make_nine_router_usage_cb
        from aigw.usage.daily_buffer import gateway_key_daily_buffer

        async with session_factory() as s:
            gk_id = await _make_gateway_key(s)

        gateway_key_daily_buffer._buffer.clear()
        with (
            patch("aigw.api_key_mode.is_db_configured", return_value=True),
            patch("aigw.db.engine.async_session_factory", session_factory),
            patch("aigw.usage.daily_buffer.async_session_factory", session_factory),
        ):
            cb = _make_nine_router_usage_cb(gk_id)
            await cb(1036, 15, "claude", cache_read_tokens=1000, cache_creation_tokens=20)
            await cb(2036, 25, "claude", cache_read_tokens=2000, cache_creation_tokens=0)
            await gateway_key_daily_buffer.flush()

        async with session_factory() as s:
            monthly = (await s.execute(select(GatewayKeyUsage))).scalars().all()
            daily = (await s.execute(select(GatewayKeyDailyUsage))).scalars().all()

        assert [(m.current_usage, m.month) for m in monthly] == [(2, time.strftime("%Y-%m"))]
        assert [(d.input_tokens, d.output_tokens, d.cache_read_tokens, d.cache_creation_tokens) for d in daily] == [
            (3072, 40, 3000, 20)
        ]


class TestDedupeMigration:
    def test_merges_duplicate_buckets_and_keeps_totals(self, fresh_db_url):
        import asyncio

        alembic_upgrade(fresh_db_url, "n0o1p2q3r4s5")

        async def seed() -> None:
            engine = create_async_engine(fresh_db_url)
            async with engine.begin() as c:
                await c.execute(text("INSERT INTO users (id, username, password_hash, role, is_active, can_create_gateway_key) VALUES (1, 'a', 'x', 'user', true, false), (2, 'b', 'x', 'user', true, false)"))
                await c.execute(text("INSERT INTO gateway_keys (id, user_id, key_hash, key_prefix, key_suffix, is_active) VALUES (1, 1, 'h1', 'p', 's', true), (2, 2, 'h2', 'p', 's', true)"))
                # Key 1: three per-request rows for one bucket (the bug); key 2: one clean row.
                await c.execute(text(
                    "INSERT INTO gateway_key_usage (gateway_key_id, month, current_usage, last_used_at, key_id) VALUES "
                    "(1, '2026-10', 1, '2026-10-01 10:00', NULL), (1, '2026-10', 1, '2026-10-03 09:00', NULL), "
                    "(1, '2026-10', 1, NULL, NULL), (2, '2026-10', 5, '2026-10-02 00:00', NULL)"
                ))
                await c.execute(text(
                    "INSERT INTO gateway_key_daily_usage (gateway_key_id, date, model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, key_id) VALUES "
                    "(1, '2026-10-03', 'm', 2000000000, 10, 5, 1, NULL), (1, '2026-10-03', 'm', 2000000000, 20, 7, 0, NULL), "
                    "(1, '2026-10-03', 'other', 1, 1, 0, 0, NULL)"
                ))
            await engine.dispose()

        async def read():
            engine = create_async_engine(fresh_db_url)
            async with engine.connect() as c:
                monthly = (await c.execute(text(
                    "SELECT gateway_key_id, current_usage, last_used_at FROM gateway_key_usage ORDER BY gateway_key_id"
                ))).all()
                daily = (await c.execute(text(
                    "SELECT model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens "
                    "FROM gateway_key_daily_usage ORDER BY model"
                ))).all()
            await engine.dispose()
            return monthly, daily

        asyncio.run(seed())
        alembic_upgrade(fresh_db_url, "o1p2q3r4s5t6")
        monthly, daily = asyncio.run(read())

        assert [tuple(r) for r in monthly] == [
            (1, 3, datetime(2026, 10, 3, 9, 0)),
            (2, 5, datetime(2026, 10, 2, 0, 0)),
        ]
        # 2 × 2e9 overflows int32: the widening must run before the merge.
        assert [tuple(r) for r in daily] == [("m", 4_000_000_000, 30, 12, 1), ("other", 1, 1, 0, 0)]


class TestAnalyticsRoute:
    @pytest.mark.asyncio
    async def test_gateway_key_analytics_reports_cache_breakdown(self, session_factory):
        from aigw.dashboard.routes_analytics import get_gateway_key_analytics

        today = datetime.now(timezone.utc).date().isoformat()
        async with session_factory() as s:
            gk_id = await _make_gateway_key(s, "bob")
            await increment_gateway_key_daily_usage(
                s, gk_id, today, 1000, 10, model="m", cache_read_tokens=900, cache_creation_tokens=50
            )
            await increment_gateway_key_daily_usage(s, gk_id, today, 500, 5, model="n", cache_read_tokens=400)
            resp = await get_gateway_key_analytics(range_key="7d", caller=None, session=s)

        assert (resp.total_input_tokens, resp.total_output_tokens) == (1500, 15)
        assert (resp.total_cache_read_tokens, resp.total_cache_creation_tokens) == (1300, 50)
        assert resp.daily_series[-1].cache_read_tokens == 1300
        [user] = resp.user_usages
        assert (user.username, user.input_tokens, user.cache_read_tokens, user.cache_creation_tokens) == (
            "bob", 1500, 1300, 50
        )
