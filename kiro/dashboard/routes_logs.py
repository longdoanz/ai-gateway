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
Dashboard routes for the real-time log viewer.

``GET /api/logs/stream`` streams WARNING+ log entries over SSE (backlog first,
then live events with heartbeat keep-alives). ``GET /api/logs/recent`` returns
the recent backlog as JSON. Both require admin access.
"""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from kiro.dashboard.deps import require_admin
from kiro.log_stream import log_stream
from kiro.db.models import User

router = APIRouter(prefix="/logs", tags=["logs"])

_HEARTBEAT_INTERVAL_SECONDS = 15


def _sse_event(entry) -> str:
    """Render one log entry as an SSE data frame."""
    return f"data: {entry.to_json()}\n\n"


async def _event_stream() -> AsyncGenerator[str, None]:
    """
    SSE generator: replay the backlog, then stream live entries.

    Emits a comment heartbeat every 15s of inactivity to keep the
    connection alive through proxies, and always unsubscribes on exit.
    """
    sid = log_stream.subscribe()
    try:
        for entry in log_stream.recent():
            yield _sse_event(entry)

        q = log_stream.subscriber_queue(sid)
        while q is not None:
            try:
                entry = await asyncio.wait_for(q.get(), timeout=_HEARTBEAT_INTERVAL_SECONDS)
                yield _sse_event(entry)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
    finally:
        log_stream.unsubscribe(sid)


@router.get("/stream")
async def stream_logs(_: User = Depends(require_admin)) -> StreamingResponse:
    """
    SSE stream of recent + live WARNING+ log entries (admin only).
    """
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/recent")
async def recent_logs(_: User = Depends(require_admin)) -> dict:
    """
    Return the recent WARNING+ log backlog as JSON (admin only).

    Useful as a non-streaming fallback and for tests.
    """
    return {
        "entries": [json.loads(entry.to_json()) for entry in log_stream.recent()],
    }
