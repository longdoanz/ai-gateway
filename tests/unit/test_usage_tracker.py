import pytest
from unittest.mock import AsyncMock, patch
from kiro.usage.tracker import track_usage


class TestTrackUsage:
    @pytest.mark.asyncio
    async def test_skip_when_tokens_zero(self):
        with patch("kiro.usage.tracker.async_session_factory") as mock_factory:
            await track_usage(key_id=1, input_tokens=0, output_tokens=0)
            mock_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_when_tokens_zero_does_not_update_cache(self):
        with patch("kiro.usage.tracker.usage_cache") as mock_cache:
            with patch("kiro.usage.tracker.async_session_factory"):
                await track_usage(key_id=1, input_tokens=0, output_tokens=0)
                mock_cache.increment.assert_not_called()

    @pytest.mark.asyncio
    async def test_proceeds_with_input_tokens(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("kiro.usage.tracker.async_session_factory", return_value=mock_session):
            with patch("kiro.usage.tracker.get_canonical_usage_key_id", new_callable=AsyncMock, return_value=1):
                with patch("kiro.usage.tracker.increment_usage", new_callable=AsyncMock) as mock_inc:
                    with patch("kiro.usage.tracker.usage_cache") as mock_cache:
                        mock_cache.increment = AsyncMock()
                        with patch("kiro.usage.tracker.daily_buffer"):
                            await track_usage(key_id=1, input_tokens=100, output_tokens=50)
                            # increment_usage(session, key_id, month, total) — total at index 3
                            assert mock_inc.call_args[0][3] == 150

    @pytest.mark.asyncio
    async def test_proceeds_with_tokens_positive(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("kiro.usage.tracker.async_session_factory", return_value=mock_session):
            with patch("kiro.usage.tracker.get_canonical_usage_key_id", new_callable=AsyncMock, return_value=2):
                with patch("kiro.usage.tracker.increment_usage", new_callable=AsyncMock) as mock_inc:
                    with patch("kiro.usage.tracker.usage_cache") as mock_cache:
                        mock_cache.increment = AsyncMock()
                        with patch("kiro.usage.tracker.daily_buffer"):
                            await track_usage(key_id=2, input_tokens=200, output_tokens=100, model="claude-sonnet-4.6")
                            # increment_usage(session, key_id, month, total) — total at index 3
                            assert mock_inc.call_args[0][3] == 300

    @pytest.mark.asyncio
    async def test_uses_canonical_key_for_same_kiro_user(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("kiro.usage.tracker.async_session_factory", return_value=mock_session):
            with patch("kiro.usage.tracker.get_canonical_usage_key_id", new_callable=AsyncMock, return_value=17) as mock_resolve:
                with patch("kiro.usage.tracker.increment_usage", new_callable=AsyncMock) as mock_inc:
                    with patch("kiro.usage.tracker.usage_cache") as mock_cache:
                        mock_cache.increment = AsyncMock()
                        with patch("kiro.usage.tracker.daily_buffer") as mock_buffer:
                            resolved = await track_usage(key_id=42, input_tokens=100, output_tokens=50, model="auto")

        assert resolved == 17
        mock_resolve.assert_awaited_once()
        assert mock_inc.call_args[0][1] == 17
        mock_cache.increment.assert_awaited_once_with(17, 150)
        mock_buffer.record.assert_called_once()
        assert mock_buffer.record.call_args[0][0] == 17
        # Check tokens passed to buffer
        assert mock_buffer.record.call_args[0][2] == 100  # input_tokens
        assert mock_buffer.record.call_args[0][3] == 50   # output_tokens
