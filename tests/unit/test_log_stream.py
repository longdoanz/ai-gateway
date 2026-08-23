# -*- coding: utf-8 -*-

"""
Unit tests for the real-time log stream (kiro.log_stream).

Verifies ring-buffer capture, level filtering, subscriber broadcast and the
non-blocking contract of the loguru sink.
"""

import asyncio
import pytest
from loguru import logger

from kiro.log_stream import LogEntry, LogStream


@pytest.fixture
def stream():
    """Fresh, isolated LogStream with sink attached."""
    s = LogStream.__new__(LogStream)
    s._initialized = False
    s.__init__()
    s.attach_sink()
    yield s
    s.detach_sink()


def _emit(level: str, message: str) -> None:
    """Emit a loguru record at the given level."""
    getattr(logger, level.lower())(message)


# ---------------------------------------------------------------------------
# Ring buffer
# ---------------------------------------------------------------------------

class TestRingBuffer:
    def test_captures_warning_and_error(self, stream):
        _emit("WARNING", "warn here")
        _emit("ERROR", "error here")
        entries = stream.recent()
        assert [e.level for e in entries] == ["WARNING", "ERROR"]
        assert [e.message for e in entries] == ["warn here", "error here"]

    def test_ignores_info_and_below(self, stream):
        _emit("INFO", "boring")
        _emit("DEBUG", "detail")
        assert stream.recent() == []

    def test_caps_buffer_at_maxlen(self):
        s = LogStream.__new__(LogStream)
        s._initialized = False
        s.__init__()
        # Force a tiny buffer to prove the cap.
        from collections import deque
        s._buffer = deque(maxlen=5)
        s.attach_sink()
        try:
            for i in range(20):
                _emit("ERROR", f"msg {i}")
            entries = s.recent()
            assert len(entries) == 5
            assert [e.message for e in entries] == ["msg 15", "msg 16", "msg 17", "msg 18", "msg 19"]
        finally:
            s.detach_sink()

    def test_recent_limit(self, stream):
        for i in range(10):
            _emit("WARNING", f"m{i}")
        entries = stream.recent(limit=3)
        assert [e.message for e in entries] == ["m7", "m8", "m9"]

    def test_recent_order_newest_last(self, stream):
        _emit("ERROR", "first")
        _emit("ERROR", "second")
        entries = stream.recent()
        assert entries[0].message == "first"
        assert entries[-1].message == "second"

    def test_entry_fields(self, stream):
        _emit("ERROR", "boom")
        entry = stream.recent()[0]
        assert entry.level == "ERROR"
        assert entry.function  # caller function captured
        assert entry.line > 0
        assert entry.name  # module path
        assert entry.time  # ISO timestamp

    def test_to_json_roundtrip(self, stream):
        _emit("ERROR", "roundtrip")
        entry = stream.recent()[0]
        import json
        data = json.loads(entry.to_json())
        assert data["message"] == "roundtrip"
        assert data["level"] == "ERROR"
        assert "time" in data and "line" in data


# ---------------------------------------------------------------------------
# Sink lifecycle
# ---------------------------------------------------------------------------

class TestSinkLifecycle:
    def test_attach_is_idempotent(self, stream):
        stream.attach_sink()
        stream.attach_sink()
        # A single emitted record should appear exactly once.
        _emit("ERROR", "once")
        assert len(stream.recent()) == 1

    def test_detach_stops_capture(self, stream):
        stream.detach_sink()
        _emit("ERROR", "not captured")
        assert stream.recent() == []

    def test_detach_idempotent(self, stream):
        stream.detach_sink()
        stream.detach_sink()  # should not raise


# ---------------------------------------------------------------------------
# Broadcast / subscribers
# ---------------------------------------------------------------------------

class TestSubscribers:
    @pytest.mark.asyncio
    async def test_no_subscribers_no_crash(self, stream):
        _emit("ERROR", "alone")
        await stream._flush_inbox()
        assert len(stream.recent()) == 1

    @pytest.mark.asyncio
    async def test_subscriber_receives_broadcast(self, stream):
        sid = stream.subscribe()
        _emit("ERROR", "hello sub")
        await stream._flush_inbox()
        q = stream.subscriber_queue(sid)
        entry = await asyncio.wait_for(q.get(), timeout=1)
        assert entry.message == "hello sub"
        stream.unsubscribe(sid)

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive(self, stream):
        sids = [stream.subscribe() for _ in range(3)]
        _emit("WARNING", "fan out")
        await stream._flush_inbox()
        for sid in sids:
            q = stream.subscriber_queue(sid)
            entry = await asyncio.wait_for(q.get(), timeout=1)
            assert entry.message == "fan out"
            stream.unsubscribe(sid)

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self, stream):
        sid = stream.subscribe()
        stream.unsubscribe(sid)
        _emit("ERROR", "nobody")
        await stream._flush_inbox()
        assert stream.subscriber_queue(sid) is None

    @pytest.mark.asyncio
    async def test_full_subscriber_is_dropped(self, stream):
        sid = stream.subscribe()
        q = stream.subscriber_queue(sid)
        # Fill the queue.
        while True:
            try:
                q.put_nowait(LogEntry("t", "ERROR", "n", "f", 1, "x"))
            except asyncio.QueueFull:
                break
        _emit("ERROR", "overflow")
        await stream._flush_inbox()
        # Subscriber got dropped because it was full.
        assert stream.subscriber_queue(sid) is None

    @pytest.mark.asyncio
    async def test_sink_does_not_block_on_full_inbox(self, stream):
        # Fill the inbox so put_nowait would drop.
        while True:
            try:
                stream._inbox.put_nowait(LogEntry("t", "ERROR", "n", "f", 1, "x"))
            except Exception:
                break
        # Emitting must not raise or block.
        _emit("ERROR", "after full inbox")
        assert True


# ---------------------------------------------------------------------------
# Start/stop drain task
# ---------------------------------------------------------------------------

class TestDrainTask:
    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, stream):
        await stream.start()
        assert stream._drain_task is not None
        await stream.start()  # idempotent
        await stream.stop()
        assert stream._drain_task is None
        await stream.stop()  # idempotent

    @pytest.mark.asyncio
    async def test_drain_task_forwards_entries(self, stream):
        await stream.start()
        try:
            sid = stream.subscribe()
            _emit("ERROR", "via drain loop")
            q = stream.subscriber_queue(sid)
            entry = await asyncio.wait_for(q.get(), timeout=2)
            assert entry.message == "via drain loop"
            stream.unsubscribe(sid)
        finally:
            await stream.stop()
