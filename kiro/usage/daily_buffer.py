import asyncio
from collections import defaultdict

from loguru import logger

from kiro.db.engine import async_session_factory
from kiro.db.repositories import increment_daily_usage

_FLUSH_INTERVAL = 60


class DailyBuffer:
    def __init__(self) -> None:
        self._buffer: dict[tuple[int, str], int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    def record(self, key_id: int, date_str: str, amount: int) -> None:
        self._buffer[(key_id, date_str)] += amount

    async def flush(self) -> None:
        if not self._buffer:
            return
        if async_session_factory is None:
            return
        async with self._lock:
            snapshot = dict(self._buffer)
            self._buffer.clear()
        if not snapshot:
            return
        try:
            async with async_session_factory() as session:
                for (key_id, date_str), credits in snapshot.items():
                    await increment_daily_usage(session, key_id, date_str, credits)
            logger.debug(f"DailyBuffer: flushed {len(snapshot)} entries")
        except Exception as e:
            logger.error(f"DailyBuffer: flush failed: {e}")
            # Restore snapshot on failure. Note: if some entries were already committed
            # before the error, they will be written again on the next flush (double-count).
            # This is an acceptable trade-off to avoid data loss.
            async with self._lock:
                for k, v in snapshot.items():
                    self._buffer[k] += v

    async def _run_loop(self) -> None:
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL)
            await self.flush()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())
        logger.info("DailyBuffer: flush task started")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.flush()
        logger.info("DailyBuffer: flushed and stopped")


daily_buffer = DailyBuffer()


class GatewayKeyDailyBuffer:
    def __init__(self) -> None:
        self._buffer: dict[tuple[int, str, int | None], int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    def record(self, gateway_key_id: int, date_str: str, amount: int, key_id: int | None = None) -> None:
        self._buffer[(gateway_key_id, date_str, key_id)] += amount

    async def flush(self) -> None:
        if not self._buffer:
            return
        if async_session_factory is None:
            return
        async with self._lock:
            snapshot = dict(self._buffer)
            self._buffer.clear()
        if not snapshot:
            return
        try:
            from kiro.db.repositories import increment_gateway_key_daily_usage
            async with async_session_factory() as session:
                for (gw_key_id, date_str, key_id), credits in snapshot.items():
                    await increment_gateway_key_daily_usage(session, gw_key_id, date_str, credits, key_id=key_id)
            logger.debug(f"GatewayKeyDailyBuffer: flushed {len(snapshot)} entries")
        except Exception as e:
            logger.error(f"GatewayKeyDailyBuffer: flush failed: {e}")
            async with self._lock:
                for k, v in snapshot.items():
                    self._buffer[k] += v

    async def _run_loop(self) -> None:
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL)
            await self.flush()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())
        logger.info("GatewayKeyDailyBuffer: flush task started")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.flush()
        logger.info("GatewayKeyDailyBuffer: flushed and stopped")


gateway_key_daily_buffer = GatewayKeyDailyBuffer()
