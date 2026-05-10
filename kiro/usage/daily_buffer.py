import asyncio

from loguru import logger

from sqlalchemy.exc import IntegrityError

from kiro.db.engine import async_session_factory
from kiro.db.repositories import increment_daily_usage

_FLUSH_INTERVAL = 60


class DailyBuffer:
    def __init__(self) -> None:
        self._buffer: dict[tuple[int, str, str], tuple[int, int]] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    def record(self, key_id: int, date_str: str, input_tokens: int, output_tokens: int, model: str = "unknown") -> None:
        key = (key_id, date_str, model)
        cur = self._buffer.get(key, (0, 0))
        self._buffer[key] = (cur[0] + input_tokens, cur[1] + output_tokens)

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
                for (key_id, date_str, model), (in_tok, out_tok) in snapshot.items():
                    try:
                        await increment_daily_usage(session, key_id, date_str, in_tok, out_tok, model=model)
                    except IntegrityError as ie:
                        msg = str(ie)
                        if "daily_usage_key_id_fkey" in msg or "foreign key" in msg.lower():
                            logger.warning(f"DailyBuffer: skipping missing key_id={key_id} during flush: {ie}")
                            continue
                        raise
            logger.debug(f"DailyBuffer: flushed {len(snapshot)} entries")
        except Exception as e:
            logger.error(f"DailyBuffer: flush failed: {e}")
            async with self._lock:
                for k, v in snapshot.items():
                    cur = self._buffer.get(k, (0, 0))
                    self._buffer[k] = (cur[0] + v[0], cur[1] + v[1])

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
        self._buffer: dict[tuple[int, str, int | None, str], tuple[int, int]] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    def record(self, gateway_key_id: int, date_str: str, input_tokens: int, output_tokens: int, model: str = "unknown", key_id: int | None = None) -> None:
        key = (gateway_key_id, date_str, key_id, model)
        cur = self._buffer.get(key, (0, 0))
        self._buffer[key] = (cur[0] + input_tokens, cur[1] + output_tokens)

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
                for (gw_key_id, date_str, key_id, model), (in_tok, out_tok) in snapshot.items():
                    try:
                        await increment_gateway_key_daily_usage(session, gw_key_id, date_str, in_tok, out_tok, model=model, key_id=key_id)
                    except IntegrityError as ie:
                        msg = str(ie)
                        if "foreign key" in msg.lower() and ("api_keys" in msg or "key_id" in msg.lower()):
                            logger.warning(f"GatewayKeyDailyBuffer: skipping missing key_id={key_id} during flush: {ie}")
                            continue
                        raise
            logger.debug(f"GatewayKeyDailyBuffer: flushed {len(snapshot)} entries")
        except Exception as e:
            logger.error(f"GatewayKeyDailyBuffer: flush failed: {e}")
            async with self._lock:
                for k, v in snapshot.items():
                    cur = self._buffer.get(k, (0, 0))
                    self._buffer[k] = (cur[0] + v[0], cur[1] + v[1])

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
