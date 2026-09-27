# -*- coding: utf-8 -*-

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

from aigw.dashboard.deps import require_admin
from aigw.log_stream import log_stream
from aigw.db.models import User

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
