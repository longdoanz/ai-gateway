# -*- coding: utf-8 -*-

"""
Unit tests for the Telegram notifier (kiro.telegram_notifier).

Verifies enable/disable gating, deduplication, cooldown, queue overflow
behaviour and the outbound HTTP payload.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from kiro.log_stream import LogEntry
from kiro.telegram_notifier import TelegramNotifier, _signature, _DEDUP_WINDOW_SECONDS


def _entry(level: str = "ERROR", message: str = "boom", name: str = "kiro.test",
           function: str = "run", line: int = 1) -> LogEntry:
    return LogEntry(time="2026-08-23T00:00:00+00:00", level=level, name=name,
                    function=function, line=line, message=message)


@pytest.fixture
def notifier(monkeypatch):
    """Fresh, isolated TelegramNotifier with Telegram enabled."""
    n = TelegramNotifier.__new__(TelegramNotifier)
    n._initialized = False
    n.__init__()
    monkeypatch.setattr("kiro.telegram_notifier.TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setattr("kiro.telegram_notifier.TELEGRAM_CHAT_ID", "test-chat-id")
    return n


class TestSignature:
    def test_signature_combines_fields(self):
        a = _entry(message="same")
        b = _entry(message="same", line=99)
        assert _signature(a) != _signature(b)

    def test_signature_same_for_same_entry(self):
        assert _signature(_entry()) == _signature(_entry())


class TestEnablement:
    def test_disabled_when_token_missing(self, monkeypatch):
        monkeypatch.setattr("kiro.telegram_notifier.TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setattr("kiro.telegram_notifier.TELEGRAM_CHAT_ID", "chat")
        n = TelegramNotifier.__new__(TelegramNotifier)
        n._initialized = False
        n.__init__()
        assert not n.is_enabled()

    def test_disabled_when_chat_missing(self, monkeypatch):
        monkeypatch.setattr("kiro.telegram_notifier.TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setattr("kiro.telegram_notifier.TELEGRAM_CHAT_ID", "")
        n = TelegramNotifier.__new__(TelegramNotifier)
        n._initialized = False
        n.__init__()
        assert not n.is_enabled()

    def test_enabled_when_both_set(self, notifier):
        assert notifier.is_enabled()

    def test_attach_sink_noop_when_disabled(self, monkeypatch):
        monkeypatch.setattr("kiro.telegram_notifier.TELEGRAM_BOT_TOKEN", "")
        n = TelegramNotifier.__new__(TelegramNotifier)
        n._initialized = False
        n.__init__()
        n.attach_sink()  # must not raise or attach
        assert n._sink_id is None


def _as_message(entry: LogEntry):
    """Wrap a LogEntry as a loguru-style Message carrying .record."""
    from datetime import datetime, timezone

    class _Msg(str):
        pass
    record = {
        "time": datetime(2026, 8, 23, tzinfo=timezone.utc),
        "level": MagicMock(name=entry.level),
        "name": entry.name,
        "function": entry.function,
        "line": entry.line,
        "message": entry.message,
    }
    record["level"].name = entry.level
    msg = _Msg(entry.message)
    msg.record = record
    return msg


class TestQueue:
    def test_sink_queues_entry(self, notifier):
        notifier._sink(_as_message(_entry()))
        assert notifier._send_queue.qsize() == 1

    def test_sink_drops_when_queue_full(self, notifier):
        # Fill the queue to capacity.
        while True:
            try:
                notifier._send_queue.put_nowait(_entry(message="fill"))
            except Exception:
                break
        notifier._sink(_as_message(_entry(message="dropped")))
        assert notifier._send_queue.qsize() == notifier._send_queue.maxsize


def _client_for(notifier):
    """Return an AsyncMock httpx client wired into the notifier."""
    client = AsyncMock()
    notifier._client = client
    return client


class TestDispatch:
    @pytest.mark.asyncio
    async def test_deduplicates_same_error_within_window(self, notifier):
        notifier._last_sent = time.monotonic() - 100  # cooldown cleared
        client = _client_for(notifier)
        client.post.return_value = MagicMock(status_code=200)
        await notifier._dispatch(_entry(message="dup"))
        await notifier._dispatch(_entry(message="dup"))
        assert client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_allows_different_errors(self, notifier):
        client = _client_for(notifier)
        client.post.return_value = MagicMock(status_code=200)
        # Reset cooldown between sends so only dedup is exercised.
        notifier._last_sent = time.monotonic() - 100
        await notifier._dispatch(_entry(message="a"))
        notifier._last_sent = time.monotonic() - 100
        await notifier._dispatch(_entry(message="b"))
        assert client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_dedup_window_clears_after_180s(self, notifier):
        client = _client_for(notifier)
        client.post.return_value = MagicMock(status_code=200)
        entry = _entry(message="aged")
        notifier._last_sent = time.monotonic() - 100
        await notifier._dispatch(entry)
        # Simulate dedup window expiry (and clear cooldown so the resend proceeds).
        with notifier._seen_lock:
            notifier._seen[_signature(entry)] = time.monotonic() - (_DEDUP_WINDOW_SECONDS + 1)
        notifier._last_sent = time.monotonic() - 100
        await notifier._dispatch(entry)
        assert client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_cooldown_drops_burst(self, notifier):
        notifier._last_sent = time.monotonic() - 100  # cooldown clear
        client = _client_for(notifier)
        client.post.return_value = MagicMock(status_code=200)
        await notifier._dispatch(_entry(message="first"))
        # Immediately dispatch again within cooldown.
        notifier._seen = {}  # bypass dedup
        await notifier._dispatch(_entry(message="second"))
        assert client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_once_on_500_then_gives_up(self, notifier):
        notifier._last_sent = time.monotonic() - 100
        client = _client_for(notifier)
        client.post.return_value = MagicMock(status_code=500, text="oops")
        await notifier._dispatch(_entry())
        assert client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_succeeds(self, notifier):
        notifier._last_sent = time.monotonic() - 100
        client = _client_for(notifier)
        client.post.side_effect = [MagicMock(status_code=500, text="oops"), MagicMock(status_code=200)]
        await notifier._dispatch(_entry())
        assert client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_network_error_does_not_raise(self, notifier):
        notifier._last_sent = time.monotonic() - 100
        client = _client_for(notifier)
        client.post.side_effect = Exception("telegram unreachable")
        await notifier._dispatch(_entry())  # must not raise
        assert client.post.call_count == 1


class TestPayload:
    @pytest.mark.asyncio
    async def test_payload_shape(self, notifier):
        notifier._last_sent = time.monotonic() - 100
        client = _client_for(notifier)
        client.post.return_value = MagicMock(status_code=200)
        await notifier._dispatch(_entry(message="hello <world>"))
        url, kwargs = client.post.call_args
        assert url[0] == "https://api.telegram.org/bot{token}/sendMessage".format(token="test-bot-token")
        payload = kwargs["json"]
        assert payload["chat_id"] == "test-chat-id"
        assert payload["parse_mode"] == "HTML"
        assert payload["disable_web_page_preview"] is True
        assert "ERROR" in payload["text"]
        assert "hello <world>" in payload["text"]
        assert "kiro.test:run:1" in payload["text"]

    def test_format_message_truncates_long(self):
        notifier = TelegramNotifier.__new__(TelegramNotifier)
        text = notifier._format_message(_entry(message="x" * 5000))
        assert len(text) <= 3501  # 3500 + ellipsis


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, notifier):
        client = AsyncMock()
        await notifier.start(client)
        assert notifier._task is not None
        await notifier.start(client)  # idempotent
        await notifier.stop()
        assert notifier._task is None
        await notifier.stop()  # idempotent

    @pytest.mark.asyncio
    async def test_start_noop_when_disabled(self, monkeypatch):
        monkeypatch.setattr("kiro.telegram_notifier.TELEGRAM_BOT_TOKEN", "")
        n = TelegramNotifier.__new__(TelegramNotifier)
        n._initialized = False
        n.__init__()
        await n.start(AsyncMock())
        assert n._task is None
