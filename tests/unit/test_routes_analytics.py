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

    def _empty():
        r = MagicMock()
        r.all.return_value = []
        return r

    # 1. daily_rows — only 1 of 7 days has data
    daily_result = MagicMock()
    daily_result.all.return_value = [
        MagicMock(date="2026-04-27", input_tokens=80, output_tokens=20),
    ]

    # 2. gw_system_daily_rows (key_id IS NULL)
    gw_system_daily_result = _empty()

    # 3. mapping_rows (KiroUserMapping)
    mapping_result = MagicMock()
    mapping_result.all.return_value = [
        MagicMock(kiro_user_id="kiro-alice", username="alice", email="alice@test.com"),
    ]

    # 4. build_kiro_email_lookup
    email_result = _empty()

    # 5. kiro_rows (ApiKey + DailyUsage totals per kiro_user_id)
    kiro_result = MagicMock()
    kiro_result.all.return_value = [
        MagicMock(kiro_user_id="kiro-alice", input_tokens=80, output_tokens=20),
    ]

    # 6. gw_pool_user_rows (pool-key gateway usage per kiro_user_id)
    gw_pool_user_result = _empty()

    # 7. gw_user_token_rows (gateway key users)
    gw_user_token_result = _empty()

    # 8. kiro_daily_rows (per kiro_user_id per date)
    kiro_daily_result = _empty()

    # 9. gw_pool_daily_rows (pool-key gateway usage per kiro_user_id per date)
    gw_pool_daily_result = _empty()

    # 10. gw_daily_rows (gateway key users per date)
    gw_daily_result = _empty()

    session.execute = AsyncMock(side_effect=[
        daily_result, gw_system_daily_result, mapping_result, _empty(), email_result,
        kiro_result, gw_pool_user_result, gw_user_token_result,
        kiro_daily_result, gw_pool_daily_result, gw_daily_result,
    ])

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
