"""Unit tests for get_overview — verify 9router/system-level gateway usage is merged."""

import datetime as _datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _row(**kwargs):
    """SQLAlchemy-like result row with attribute access."""
    r = MagicMock()
    for k, v in kwargs.items():
        setattr(r, k, v)
    return r


def _all(*rows):
    """Mock execute result where .all() returns list of rows, .scalar_one() returns rows[0]."""
    m = MagicMock()
    m.all.return_value = list(rows)
    m.scalar_one.return_value = rows[0] if rows else None
    return m


def _one(*values):
    """Mock execute result where .one() returns the values as a tuple (unpackable)."""
    row = tuple(values)
    m = MagicMock()
    m.one.return_value = row
    return m


def _freeze_clock(the_date: date):
    """Replace routes_overview.datetime so datetime.now() returns fixed dates."""

    class _Frozen(_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(the_date.year, the_date.month, the_date.day, tzinfo=tz)

    return patch("kiro.dashboard.routes_overview.datetime", _Frozen)


async def _call_overview(session: AsyncMock, today: date, granularity: str = "daily"):
    from kiro.dashboard.routes_overview import get_overview

    fake_user = MagicMock(id=1, username="admin", role="admin")

    with _freeze_clock(today), \
         patch("kiro.dashboard.routes_overview.get_credit_snapshots", new_callable=AsyncMock, return_value=[]):
        return await get_overview(granularity, caller=fake_user, session=session)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_merges_gw_system_into_daily_usage():
    """GatewayKeyDailyUsage (key_id IS NULL) must be added to daily_usage chart."""
    session = AsyncMock()
    today = date(2026, 7, 16)

    session.execute = AsyncMock(side_effect=[
        _one(0, 0),                                                               # 1  — per_user_subq .one()
        _all(3),                                                                  # 2  — active_keys .scalar_one()
        _all(),                                                                   # 3  — active_kiro_rows .all()
        _all(),                                                                   # 4  — active_gw_rows .all()
        _all(),                                                                   # 5  — total_kiro_rows .all()
        _all(),                                                                   # 6  — total_gw_rows .all()
        _all(_row(date="2026-07-16", input_tokens=100, output_tokens=50)),        # 7  — daily_rows .all()
        _all(_row(date="2026-07-16", input_tokens=40, output_tokens=10)),        # 8  — gw_system_daily_rows .all()
        _one(100, 50),                                                            # 9  — own_token_result .one()
        _one(40, 10),                                                            # 10 — gw_sys_token_result .one()
        _one(40, 10),                                                            # 11 — gw_token_result .one()
    ])

    result = await _call_overview(session, today)

    assert result.total_input_tokens == 140   # 100 own + 40 gw
    assert result.total_output_tokens == 60   # 50 own + 10 gw
    today_entry = result.daily_usage[-1]
    assert today_entry.input_tokens == 140
    assert today_entry.output_tokens == 60


@pytest.mark.asyncio
async def test_no_gateway_data_still_works():
    """Backward compat: empty GatewayKeyDailyUsage → same totals as before."""
    session = AsyncMock()
    today = date(2026, 7, 16)

    session.execute = AsyncMock(side_effect=[
        _one(0, 0),                                                               # 1
        _all(3),                                                                  # 2
        _all(), _all(), _all(), _all(),                                           # 3-6
        _all(_row(date="2026-07-16", input_tokens=100, output_tokens=50)),        # 7
        _all(),                                                                   # 8  — gw_system_daily EMPTY
        _one(100, 50),                                                            # 9
        _one(0, 0),                                                              # 10
        _one(0, 0),                                                              # 11
    ])

    result = await _call_overview(session, today)

    assert result.total_input_tokens == 100
    assert result.total_output_tokens == 50
    assert result.daily_usage[-1].input_tokens == 100
    assert result.daily_usage[-1].output_tokens == 50


@pytest.mark.asyncio
async def test_weekly_granularity_merges_gw():
    """Weekly aggregation includes system-level gateway usage."""
    session = AsyncMock()
    today = date(2026, 7, 16)  # Thursday

    session.execute = AsyncMock(side_effect=[
        _one(0, 0),                                                               # 1
        _all(3),                                                                  # 2
        _all(), _all(), _all(), _all(),                                           # 3-6
        _all(
            _row(date="2026-07-13", input_tokens=50, output_tokens=20),
            _row(date="2026-07-14", input_tokens=60, output_tokens=30),
        ),                                                                        # 7
        _all(
            _row(date="2026-07-13", input_tokens=10, output_tokens=5),
            _row(date="2026-07-14", input_tokens=15, output_tokens=8),
        ),                                                                        # 8
        _one(110, 50),                                                            # 9
        _one(25, 13),                                                            # 10
        _one(25, 13),                                                            # 11
    ])

    result = await _call_overview(session, today, "weekly")

    assert result.total_input_tokens == 135
    assert result.total_output_tokens == 63
    # 90-day range from July 16 → ~14 ISO weeks
    assert len(result.daily_usage) == 14
    last = result.daily_usage[-1]
    assert last.date == "2026-07-13"
    assert last.input_tokens == 135
    assert last.output_tokens == 63
    for entry in result.daily_usage[:-1]:
        assert entry.input_tokens == 0
        assert entry.output_tokens == 0


@pytest.mark.asyncio
async def test_monthly_granularity_merges_gw():
    """Monthly aggregation includes system-level gateway usage."""
    session = AsyncMock()
    today = date(2026, 7, 16)

    session.execute = AsyncMock(side_effect=[
        _one(0, 0),                                                               # 1
        _all(3),                                                                  # 2
        _all(), _all(), _all(), _all(),                                           # 3-6
        _all(_row(date="2026-07-10", input_tokens=100, output_tokens=50)),        # 7
        _all(_row(date="2026-07-10", input_tokens=30, output_tokens=15)),        # 8
        _one(100, 50),                                                            # 9
        _one(30, 15),                                                            # 10
        _one(30, 15),                                                            # 11
    ])

    result = await _call_overview(session, today, "monthly")

    assert result.total_input_tokens == 130
    assert result.total_output_tokens == 65

    # 6 months: 2026-01 → 2026-07, only last has data
    assert len(result.daily_usage) == 7
    last = result.daily_usage[-1]
    assert last.date == "2026-07"
    assert last.input_tokens == 130
    assert last.output_tokens == 65
    for entry in result.daily_usage[:-1]:
        assert entry.input_tokens == 0
        assert entry.output_tokens == 0


@pytest.mark.asyncio
async def test_disjoint_dates_no_overlap():
    """Gateway usage on a different day from own usage — both appear."""
    session = AsyncMock()
    today = date(2026, 7, 16)

    session.execute = AsyncMock(side_effect=[
        _one(0, 0),                                                               # 1
        _all(3),                                                                  # 2
        _all(), _all(), _all(), _all(),                                           # 3-6
        _all(_row(date="2026-07-10", input_tokens=100, output_tokens=50)),        # 7
        _all(_row(date="2026-07-15", input_tokens=80, output_tokens=40)),        # 8
        _one(100, 50),                                                            # 9
        _one(80, 40),                                                            # 10
        _one(80, 40),                                                            # 11
    ])

    result = await _call_overview(session, today)

    assert result.total_input_tokens == 180
    assert result.total_output_tokens == 90

    dates = {d.date: (d.input_tokens, d.output_tokens) for d in result.daily_usage}
    assert dates["2026-07-10"] == (100, 50)   # own only
    assert dates["2026-07-15"] == (80, 40)    # gw only
    assert dates["2026-07-16"] == (0, 0)      # today, no data


@pytest.mark.asyncio
async def test_http_smoke_route_is_registered():
    """Smoke: GET /overview route is mounted — verify FastAPI wiring."""
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from kiro.dashboard.routes_overview import router

    app = FastAPI()
    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/overview")
    assert resp.status_code in (200, 422, 500)  # route exists — 500 from uninitialized deps is fine

