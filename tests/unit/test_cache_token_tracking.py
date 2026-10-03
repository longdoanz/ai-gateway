"""Prompt-cache token breakdown is threaded from the 9router callbacks to the DB."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aigw.usage.daily_buffer import GatewayKeyDailyBuffer


def _mock_session_factory():
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


class TestGatewayKeyDailyBuffer:
    @pytest.mark.asyncio
    async def test_accumulates_and_flushes_cache_tokens(self):
        buf = GatewayKeyDailyBuffer()
        buf.record(22, "2026-10-03", 1000, 10, model="m", cache_read_tokens=900, cache_creation_tokens=50)
        buf.record(22, "2026-10-03", 2000, 20, model="m", cache_read_tokens=1900)
        increment = AsyncMock()

        with (
            patch("aigw.usage.daily_buffer.async_session_factory", _mock_session_factory()),
            patch("aigw.db.repositories.increment_gateway_key_daily_usage", increment),
        ):
            await buf.flush()

        increment.assert_awaited_once()
        args, kwargs = increment.call_args
        assert args[1:5] == (22, "2026-10-03", 3000, 30)
        assert kwargs["cache_read_tokens"] == 2800
        assert kwargs["cache_creation_tokens"] == 50

    @pytest.mark.asyncio
    async def test_failed_flush_requeues_cache_tokens(self):
        buf = GatewayKeyDailyBuffer()
        buf.record(22, "2026-10-03", 100, 1, model="m", cache_read_tokens=90, cache_creation_tokens=5)

        with (
            patch("aigw.usage.daily_buffer.async_session_factory", _mock_session_factory()),
            patch("aigw.db.repositories.increment_gateway_key_daily_usage", AsyncMock(side_effect=RuntimeError("db down"))),
        ):
            await buf.flush()

        assert buf._buffer[(22, "2026-10-03", None, "m")] == (100, 1, 90, 5)


class TestUsageCallbacks:
    @pytest.mark.asyncio
    async def test_gateway_key_callback_forwards_cache_tokens(self):
        from aigw.api_key_mode import _make_nine_router_usage_cb

        track = AsyncMock()
        with (
            patch("aigw.api_key_mode.is_db_configured", return_value=True),
            patch("aigw.api_key_mode._track_gateway_key_usage", track),
        ):
            cb = _make_nine_router_usage_cb(22)
            await cb(1036, 15, "claude", cache_read_tokens=1000, cache_creation_tokens=20)

        kwargs = track.call_args.kwargs
        assert track.call_args.args == (22, 1036, 15)
        assert kwargs["cache_read_tokens"] == 1000
        assert kwargs["cache_creation_tokens"] == 20

    @pytest.mark.asyncio
    async def test_service_account_callback_forwards_cache_tokens(self):
        from aigw.service_accounts import make_service_account_usage_cb

        daily = AsyncMock()
        with (
            patch("aigw.service_accounts._is_db_configured", return_value=True),
            patch("aigw.db.engine.async_session_factory", _mock_session_factory()),
            patch("aigw.db.repositories.increment_service_account_usage", AsyncMock()),
            patch("aigw.db.repositories.increment_service_account_daily_usage", daily),
        ):
            cb = make_service_account_usage_cb(7)
            await cb(1036, 15, "claude", cache_read_tokens=1000, cache_creation_tokens=20)

        assert daily.call_args.args[3] == 1036
        assert daily.call_args.kwargs["cache_read_tokens"] == 1000
        assert daily.call_args.kwargs["cache_creation_tokens"] == 20
