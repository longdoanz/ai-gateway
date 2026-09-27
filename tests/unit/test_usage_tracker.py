import pytest
from unittest.mock import AsyncMock, patch
from aigw.usage.tracker import track_usage


class TestTrackUsage:
    @pytest.mark.asyncio
    async def test_skip_when_tokens_zero(self):
        with patch("aigw.usage.tracker.async_session_factory") as mock_factory:
            await track_usage(key_id=1, input_tokens=0, output_tokens=0)
            mock_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_when_tokens_zero_does_not_update_cache(self):
        with patch("aigw.usage.tracker.usage_cache") as mock_cache:
            with patch("aigw.usage.tracker.async_session_factory"):
                await track_usage(key_id=1, input_tokens=0, output_tokens=0)
                mock_cache.increment.assert_not_called()

    @pytest.mark.asyncio
    async def test_proceeds_with_input_tokens(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aigw.usage.tracker.async_session_factory", return_value=mock_session):
            with patch("aigw.usage.tracker.increment_usage", new_callable=AsyncMock) as mock_inc:
                with patch("aigw.usage.tracker.usage_cache") as mock_cache:
                    mock_cache.increment = AsyncMock()
                    with patch("aigw.usage.tracker.daily_buffer"):
                        await track_usage(key_id=1, input_tokens=100, output_tokens=50)
                        # increment_usage counts requests (1 per call), not tokens
                        assert mock_inc.call_args[0][3] == 1

    @pytest.mark.asyncio
    async def test_proceeds_with_tokens_positive(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aigw.usage.tracker.async_session_factory", return_value=mock_session):
            with patch("aigw.usage.tracker.increment_usage", new_callable=AsyncMock) as mock_inc:
                with patch("aigw.usage.tracker.usage_cache") as mock_cache:
                    mock_cache.increment = AsyncMock()
                    with patch("aigw.usage.tracker.daily_buffer"):
                        await track_usage(key_id=2, input_tokens=200, output_tokens=100, model="claude-sonnet-4.6")
                        # increment_usage counts requests (1 per call), not tokens
                        assert mock_inc.call_args[0][3] == 1

    @pytest.mark.asyncio
    async def test_returns_key_id_used_for_tracking(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aigw.usage.tracker.async_session_factory", return_value=mock_session):
            with patch("aigw.usage.tracker.increment_usage", new_callable=AsyncMock) as mock_inc:
                with patch("aigw.usage.tracker.usage_cache") as mock_cache:
                    mock_cache.increment = AsyncMock()
                    with patch("aigw.usage.tracker.daily_buffer") as mock_buffer:
                        resolved = await track_usage(key_id=42, input_tokens=100, output_tokens=50, model="auto")

        assert resolved == 42
        assert mock_inc.call_args[0][1] == 42
        mock_cache.increment.assert_awaited_once_with(42, 1)
        mock_buffer.record.assert_called_once()
        assert mock_buffer.record.call_args[0][0] == 42
        # Check tokens passed to buffer
        assert mock_buffer.record.call_args[0][2] == 100  # input_tokens
        assert mock_buffer.record.call_args[0][3] == 50   # output_tokens
