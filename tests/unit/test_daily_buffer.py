import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from kiro.usage.daily_buffer import DailyBuffer


@pytest.mark.asyncio
async def test_record_accumulates():
    buf = DailyBuffer()
    buf.record(1, "2026-04-27", 10)
    buf.record(1, "2026-04-27", 5)
    buf.record(2, "2026-04-27", 20)
    assert buf._buffer[(1, "2026-04-27")] == 15
    assert buf._buffer[(2, "2026-04-27")] == 20


@pytest.mark.asyncio
async def test_flush_clears_buffer():
    buf = DailyBuffer()
    buf.record(1, "2026-04-27", 10)

    with patch("kiro.usage.daily_buffer.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("kiro.usage.daily_buffer.increment_daily_usage", new_callable=AsyncMock):
            await buf.flush()

    assert len(buf._buffer) == 0


@pytest.mark.asyncio
async def test_flush_empty_buffer_is_noop():
    buf = DailyBuffer()
    with patch("kiro.usage.daily_buffer.async_session_factory") as mock_factory:
        await buf.flush()
    mock_factory.assert_not_called()


@pytest.mark.asyncio
async def test_graceful_shutdown_drains():
    buf = DailyBuffer()
    buf.record(1, "2026-04-27", 99)
    flushed = []

    async def fake_flush():
        flushed.append(dict(buf._buffer))
        buf._buffer.clear()

    buf.flush = fake_flush
    await buf.stop()
    assert len(flushed) == 1
    assert flushed[0] == {(1, "2026-04-27"): 99}


@pytest.mark.asyncio
async def test_flush_restores_buffer_on_error():
    """Verify buffer is restored when DB write fails."""
    buf = DailyBuffer()
    buf.record(1, "2026-04-27", 50)

    with patch("kiro.usage.daily_buffer.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("kiro.usage.daily_buffer.increment_daily_usage", new_callable=AsyncMock) as mock_inc:
            mock_inc.side_effect = Exception("DB error")
            await buf.flush()

    # Buffer should be restored after failure
    assert buf._buffer[(1, "2026-04-27")] == 50
