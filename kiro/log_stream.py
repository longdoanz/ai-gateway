# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Real-time log capture for the webui log viewer.

Attaches a loguru sink that captures WARNING+ records (no existing call
sites are modified), keeps a bounded ring buffer of recent entries and
broadcasts new entries to live SSE subscribers.

Threading model
---------------
Loguru may invoke a sink from an arbitrary thread (uvicorn worker threads,
asyncio executor threads). The sink is therefore synchronous and never
touches asyncio objects: it only appends to the ring buffer (deque is
thread-safe for append from a single producer) and pushes into a
thread-safe ``queue.Queue`` inbox. A drain task running on the event loop
forwards inbox entries to each subscriber's ``asyncio.Queue``.

Nothing on the hot path ever blocks: all ``put_nowait`` calls drop the
entry when a queue is full instead of waiting.
"""

import asyncio
import json
import queue
import threading
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

from loguru import logger

from kiro.config import LOG_STREAM_BUFFER_SIZE

_LEVEL_MIN = "WARNING"


@dataclass
class LogEntry:
    """A single captured log record, serialized for SSE/JSON delivery."""

    time: str
    level: str
    name: str
    function: str
    line: int
    message: str

    def to_json(self) -> str:
        """Serialize this entry to a JSON string (SSE data payload)."""
        return json.dumps(asdict(self), ensure_ascii=False)

    @staticmethod
    def from_record(record) -> "LogEntry":
        """Build a LogEntry from a loguru record dict."""
        return LogEntry(
            time=record["time"].astimezone(timezone.utc).isoformat(),
            level=record["level"].name,
            name=record["name"],
            function=record["function"],
            line=record["line"],
            message=str(record["message"]),
        )


class LogStream:
    """
    Singleton log capture and broadcast hub.

    Attributes:
        _buffer: Bounded ring buffer of recent entries (oldest dropped first).
        _inbox: Thread-safe handoff queue filled by the loguru sink.
        _subscribers: Active SSE subscribers keyed by id.
    """

    _instance: Optional["LogStream"] = None

    def __new__(cls) -> "LogStream":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._buffer: Deque[LogEntry] = deque(maxlen=LOG_STREAM_BUFFER_SIZE)
        self._inbox: queue.Queue = queue.Queue(maxsize=2000)
        self._subscribers: Dict[int, asyncio.Queue] = {}
        self._subscribers_lock = threading.Lock()
        self._next_subscriber_id = 0
        self._sink_id: Optional[int] = None
        self._drain_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Sink lifecycle
    # ------------------------------------------------------------------

    def attach_sink(self, level: str = _LEVEL_MIN) -> None:
        """
        Attach the capture sink to loguru.

        Idempotent: if a sink is already attached, this is a no-op.

        Args:
            level: Minimum log level to capture (default WARNING).
        """
        if self._sink_id is not None:
            return
        self._sink_id = logger.add(
            self._sink,
            level=level,
            colorize=False,
            format="{message}",  # message carries .record; format string is irrelevant
        )

    def detach_sink(self) -> None:
        """Detach the capture sink from loguru. Idempotent."""
        if self._sink_id is None:
            return
        try:
            logger.remove(self._sink_id)
        except ValueError:
            # Sink already removed externally.
            pass
        self._sink_id = None

    # ------------------------------------------------------------------
    # Loguru sink (runs on arbitrary threads — must not block or await)
    # ------------------------------------------------------------------

    def _sink(self, message) -> None:
        """
        Loguru sink: capture a WARNING+ record.

        Runs on the thread that emitted the log. Never blocks, never awaits
        and never raises — failures are swallowed so logging never affects
        the caller.

        Args:
            message: A loguru ``Message`` (str subclass) carrying ``.record``.
        """
        try:
            entry = LogEntry.from_record(message.record)
            self._buffer.append(entry)
            try:
                self._inbox.put_nowait(entry)
            except queue.Full:
                # Drop instead of blocking; the backlog is only best-effort.
                pass
        except Exception:
            # Logging must never propagate into the emitting code path.
            pass

    # ------------------------------------------------------------------
    # Event-loop drain task
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the drain task on the current event loop. Idempotent."""
        if self._drain_task is not None:
            return
        self._drain_task = asyncio.create_task(self._drain_loop(), name="log-stream-drain")

    async def stop(self) -> None:
        """Stop the drain task and drain any remaining inbox entries. Idempotent."""
        task = self._drain_task
        self._drain_task = None
        if task is not None:
            # The drain loop blocks on a threadpool queue.get(); cancelling the
            # task cannot stop that thread. Signal shutdown via a sentinel so
            # the loop exits cleanly, then await it.
            try:
                self._inbox.put_nowait(None)
            except queue.Full:
                task.cancel()
            await task
        await self._flush_inbox()

    async def _flush_inbox(self) -> None:
        """Forward any entries still in the inbox to subscribers."""
        while True:
            try:
                entry = self._inbox.get_nowait()
            except queue.Empty:
                break
            await self._broadcast(entry)

    async def _drain_loop(self) -> None:
        """Forward inbox entries to subscribers as they arrive."""
        while True:
            try:
                entry = await asyncio.to_thread(self._inbox.get)
            except Exception:
                break
            if entry is None:
                break
            await self._broadcast(entry)

    async def _broadcast(self, entry: LogEntry) -> None:
        """
        Push an entry to every active subscriber queue.

        Slow/full subscriber queues are dropped; a subscriber that is
        repeatedly full is unsubscribed.

        Args:
            entry: The log entry to broadcast.
        """
        with self._subscribers_lock:
            ids = list(self._subscribers.keys())
        for sid in ids:
            with self._subscribers_lock:
                q = self._subscribers.get(sid)
            if q is None:
                continue
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                # Slow consumer: drop the entry. If the queue stays full on
                # the next drain pass, the subscriber's own read timeout will
                # end it; proactively unsubscribing here is enough.
                self.unsubscribe(sid)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recent(self, limit: Optional[int] = None) -> list[LogEntry]:
        """
        Return the most recent captured entries, newest last.

        Args:
            limit: Maximum number of entries (defaults to the full buffer).

        Returns:
            The entries in chronological order.
        """
        entries = list(self._buffer)
        if limit is not None and limit < len(entries):
            return entries[-limit:]
        return entries

    def subscribe(self) -> int:
        """
        Register a new subscriber and return its id.

        Returns:
            A unique subscriber id, used with :meth:`unsubscribe`.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._subscribers_lock:
            self._next_subscriber_id += 1
            sid = self._next_subscriber_id
            self._subscribers[sid] = q
        return sid

    def unsubscribe(self, sid: int) -> None:
        """Remove a subscriber by id (no-op if unknown)."""
        with self._subscribers_lock:
            self._subscribers.pop(sid, None)

    def subscriber_queue(self, sid: int) -> Optional[asyncio.Queue]:
        """Return the asyncio.Queue for a subscriber id (or None)."""
        with self._subscribers_lock:
            return self._subscribers.get(sid)


# Module-level singleton.
log_stream = LogStream()
