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
Telegram error notifications for ERROR-level logs.

Records are handed off from the loguru sink through a bounded, thread-safe
``queue.Queue`` (drop-on-full, never blocking the request path) and sent by
a background asyncio task via ``httpx``.

Anti-spam:
- Cooldown: at most one message per ``TELEGRAM_MIN_INTERVAL`` seconds;
  excess records are dropped and counted.
- Deduplication: the same error signature is sent at most once per 3 minutes.

When ``TELEGRAM_BOT_TOKEN``/``TELEGRAM_CHAT_ID`` are not configured the
notifier is disabled and no code path runs.
"""

import asyncio
import queue
import threading
import time
from typing import Dict, Optional

import httpx
from loguru import logger

from kiro.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_LOG_LEVEL,
    TELEGRAM_MIN_INTERVAL,
)
from kiro.log_stream import LogEntry

_DEDUP_WINDOW_SECONDS = 180  # 3 minutes
_QUEUE_MAXSIZE = 200
_MSG_MAX_CHARS = 3500  # Telegram limit is 4096; leave headroom
_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


def _signature(entry: LogEntry) -> str:
    """Fingerprint a log entry for deduplication."""
    return f"{entry.level}|{entry.name}|{entry.function}|{entry.line}|{entry.message}"


class TelegramNotifier:
    """
    Async Telegram error notifier.

    Attributes:
        _send_queue: Thread-safe inbox filled from the sink (drop-on-full).
        _seen: Map of signature -> last-sent epoch, for 3-minute dedup.
    """

    _instance: Optional["TelegramNotifier"] = None

    def __new__(cls) -> "TelegramNotifier":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._send_queue: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._sink_id: Optional[int] = None
        self._last_sent: float = 0.0
        self._seen: Dict[str, float] = {}
        self._seen_lock = threading.Lock()

    def is_enabled(self) -> bool:
        """True when bot token and chat id are both configured."""
        return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

    def attach_sink(self) -> None:
        """
        Attach a loguru sink feeding this notifier (level: TELEGRAM_LOG_LEVEL).

        Idempotent. No-op when disabled. The sink is synchronous and
        non-blocking; it only pushes into the send queue.
        """
        if not self.is_enabled():
            return
        if self._sink_id is not None:
            return
        self._sink_id = logger.add(
            self._sink,
            level=TELEGRAM_LOG_LEVEL,
            colorize=False,
            format="{message}",
        )

    def detach_sink(self) -> None:
        """Detach the Telegram sink. Idempotent."""
        if self._sink_id is None:
            return
        try:
            logger.remove(self._sink_id)
        except ValueError:
            pass
        self._sink_id = None

    def _sink(self, message) -> None:
        """
        Loguru sink: queue an ERROR-level record for delivery.

        Runs on the emitting thread. Never blocks, never awaits, never raises.

        Args:
            message: A loguru ``Message`` (str subclass) carrying ``.record``.
        """
        try:
            entry = LogEntry.from_record(message.record)
            self._send_queue.put_nowait(entry)
        except queue.Full:
            logger.warning("Telegram notifier: send queue full, dropping log entry")
        except Exception:
            pass

    async def start(self, client: httpx.AsyncClient) -> None:
        """
        Start the background drain task.

        Args:
            client: Shared httpx client used for outbound delivery.
        """
        if not self.is_enabled():
            return
        if self._task is not None:
            return
        self._client = client
        self._task = asyncio.create_task(self._drain_loop(), name="telegram-notifier")

    async def stop(self) -> None:
        """Stop the background task and drain any pending sends."""
        task = self._task
        self._task = None
        if task is not None:
            # The drain loop blocks on a threadpool queue.get(); cancelling the
            # task cannot stop that thread. Signal shutdown via a sentinel so
            # the loop exits cleanly, then await it.
            try:
                self._send_queue.put_nowait(None)
            except queue.Full:
                task.cancel()
            await task

    async def _drain_loop(self) -> None:
        """Drain the send queue and dispatch Telegram messages."""
        while True:
            try:
                entry = await asyncio.to_thread(self._send_queue.get)
            except Exception:
                break
            if entry is None:
                break
            await self._dispatch(entry)

    async def _dispatch(self, entry: LogEntry) -> None:
        """Apply dedup + cooldown and send a single message."""
        # Deduplicate: same error signature within 3 minutes -> drop.
        sig = _signature(entry)
        now = time.monotonic()
        with self._seen_lock:
            last = self._seen.get(sig)
            if last is not None and now - last < _DEDUP_WINDOW_SECONDS:
                return
            self._seen[sig] = now
            self._seen = {k: v for k, v in self._seen.items() if now - v < _DEDUP_WINDOW_SECONDS}

        # Cooldown: at most one send per interval.
        if now - self._last_sent < TELEGRAM_MIN_INTERVAL:
            logger.warning("Telegram notifier: rate-limited, dropping log entry")
            return
        self._last_sent = now

        await self._send(entry)

    async def _send(self, entry: LogEntry) -> None:
        """POST one message to Telegram with a single bounded retry."""
        if self._client is None:
            return
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": self._format_message(entry),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        url = _API_BASE.format(token=TELEGRAM_BOT_TOKEN)
        try:
            resp = await self._client.post(url, json=payload, timeout=10.0)
            if resp.status_code == 200:
                return
            if resp.status_code >= 500:
                # One bounded retry for transient server errors.
                resp = await self._client.post(url, json=payload, timeout=10.0)
                if resp.status_code == 200:
                    return
            logger.warning(
                "Telegram notifier: send failed (status %s): %.200s", resp.status_code, resp.text
            )
        except Exception as e:
            # Telegram down / network error — drop and log, never block.
            logger.warning("Telegram notifier: send error: %s", e)

    @staticmethod
    def _format_message(entry: LogEntry) -> str:
        """Format a log entry as a Telegram HTML message (truncated)."""
        text = (
            f"<b>{entry.level}</b> {entry.time}\n"
            f"<code>{entry.name}:{entry.function}:{entry.line}</code>\n"
            f"{entry.message}"
        )
        if len(text) > _MSG_MAX_CHARS:
            text = text[:_MSG_MAX_CHARS] + "…"
        return text


# Module-level singleton.
telegram_notifier = TelegramNotifier()
