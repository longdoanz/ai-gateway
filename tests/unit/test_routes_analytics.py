import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from kiro.dashboard.routes_analytics import router
from kiro.dashboard.deps import get_current_user
from kiro.db.engine import get_session

app = FastAPI()
app.include_router(router)  # router already has prefix="/overview"

fake_user = MagicMock(id=1, username="admin", role="admin")

app.dependency_overrides[get_current_user] = lambda: fake_user
app.dependency_overrides[get_session] = lambda: AsyncMock()


@pytest.mark.asyncio
async def test_analytics_returns_all_fields():
    with patch("kiro.dashboard.routes_analytics._aggregate_analytics", new_callable=AsyncMock) as mock_agg:
        from kiro.dashboard.schemas import AnalyticsResponse
        mock_agg.return_value = AnalyticsResponse(
            time_range="7d",
            daily_series=[],
            user_tokens=[],
            top_users=[],
            token_share=[],
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/overview/analytics?range=7d")
        assert resp.status_code == 200
        data = resp.json()
        assert data["time_range"] == "7d"
        assert "daily_series" in data
        assert "user_tokens" in data
        assert "top_users" in data
        assert "token_share" in data


@pytest.mark.asyncio
async def test_analytics_invalid_range_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/overview/analytics?range=999d")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analytics_default_range_is_7d():
    with patch("kiro.dashboard.routes_analytics._aggregate_analytics", new_callable=AsyncMock) as mock_agg:
        from kiro.dashboard.schemas import AnalyticsResponse
        mock_agg.return_value = AnalyticsResponse(
            time_range="7d", daily_series=[], user_tokens=[], top_users=[], token_share=[]
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/overview/analytics")
        assert resp.status_code == 200
        mock_agg.assert_called_once()
        call_kwargs = mock_agg.call_args
        assert call_kwargs.kwargs.get("range_key") == "7d" or call_kwargs.args[1] == "7d"


@pytest.mark.asyncio
async def test_aggregate_analytics_zero_fills_missing_dates():
    """Verify zero-fill produces correct number of entries and fills gaps."""
    from kiro.dashboard.routes_analytics import _aggregate_analytics

    session = AsyncMock()

    # daily_rows query returns only 1 of 7 days
    daily_result = MagicMock()
    daily_result.all.return_value = [
        MagicMock(date="2026-04-27", input_tokens=80, output_tokens=20),
    ]

    # gw_daily_rows query (gateway daily usage to subtract)
    gw_daily_result = MagicMock()
    gw_daily_result.all.return_value = []

    # kiro_rows query returns 1 kiro user
    kiro_result = MagicMock()
    kiro_result.all.return_value = [
        MagicMock(kiro_user_id="kiro-alice", input_tokens=80, output_tokens=20),
    ]

    # gw_user_rows query (gateway per-user usage to subtract)
    gw_user_result = MagicMock()
    gw_user_result.all.return_value = []

    # build_kiro_email_lookup query
    email_result = MagicMock()
    email_result.all.return_value = []

    # mapping_rows query
    mapping_result = MagicMock()
    mapping_result.all.return_value = [
        MagicMock(kiro_user_id="kiro-alice", username="alice", email="alice@test.com"),
    ]

    # gw_user_token_rows query (gateway key user tokens for merged view)
    gw_user_token_result = MagicMock()
    gw_user_token_result.all.return_value = []

    session.execute = AsyncMock(side_effect=[daily_result, gw_daily_result, kiro_result, gw_user_result, email_result, mapping_result, gw_user_token_result])

    from datetime import date
    with patch("kiro.dashboard.routes_analytics.dt") as mock_dt:
        mock_dt.now.return_value.date.return_value = date(2026, 4, 27)
        result = await _aggregate_analytics(session, "7d")

    assert len(result.daily_series) == 7
    # Only 2026-04-27 has data, rest are zero
    last_day = result.daily_series[-1]
    assert last_day.date == "2026-04-27"
    assert last_day.input_tokens == 80
    assert last_day.output_tokens == 20
    # All other days are zero
    for entry in result.daily_series[:-1]:
        assert entry.input_tokens == 0
        assert entry.output_tokens == 0

    # User percentage
    assert len(result.top_users) == 1
    assert result.top_users[0].share_pct == 100.0
    assert result.top_users[0].display_name == "alice"


@pytest.mark.asyncio
async def test_aggregate_kiro_credit_usage_uses_normalized_d_prefix_when_name_missing():
    from kiro.dashboard.routes_analytics import _aggregate_kiro_credit_usage

    session = AsyncMock()

    usage_result = MagicMock()
    usage_result.all.return_value = [
        MagicMock(kiro_user_id="d-90660b1967.04e88498-e0d1-7084-2da6-8600557782e4", used_credit=12, quota=100),
    ]

    fallback_result = MagicMock()
    fallback_result.all.return_value = []

    gw_pool_result = MagicMock()
    gw_pool_result.all.return_value = []

    mapping_result = MagicMock()
    mapping_result.all.return_value = [
        MagicMock(
            kiro_user_id="d-90660b1967.04e88498-e0d1-7084-2da6-8600557782e4",
            username=None,
            email=None,
        ),
    ]

    session.execute = AsyncMock(side_effect=[usage_result, fallback_result, gw_pool_result, mapping_result])

    result = await _aggregate_kiro_credit_usage(session, "2026-05")

    assert len(result.users) == 1
    user = result.users[0]
    assert user.kiro_user_id == "d-90660b1967.04e88498-e0d1-7084-2da6-8600557782e4"
    assert user.display_name == "04e88498-e0d1-7084-2da6-8600557782e4"
    assert user.username is None
    assert user.email is None
