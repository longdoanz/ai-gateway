import asyncio
import time
from typing import Optional


class TokenCache:
    """Simple in-process TTL cache mapping key_hash -> (key_id, expiry_ts).

    Methods are async to be safely used from async code paths.
    """

    def __init__(self, ttl: int = 300):
        self._ttl = ttl
        self._data: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key_hash: str) -> Optional[int]:
        async with self._lock:
            item = self._data.get(key_hash)
            if not item:
                return None
            key_id, expiry = item
            if time.time() >= expiry:
                # expired
                self._data.pop(key_hash, None)
                return None
            return key_id

    async def set(self, key_hash: str, key_id: int) -> None:
        async with self._lock:
            self._data[key_hash] = (key_id, time.time() + self._ttl)

    async def invalidate_by_key_hash(self, key_hash: str) -> None:
        async with self._lock:
            self._data.pop(key_hash, None)

    async def invalidate_by_key_id(self, key_id: int) -> None:
        async with self._lock:
            to_remove = [k for k, v in self._data.items() if v[0] == key_id]
            for k in to_remove:
                self._data.pop(k, None)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()

    def clear_sync(self) -> None:
        # Synchronous clear for test fixtures that run outside event loop.
        self._data.clear()


token_cache = TokenCache()
