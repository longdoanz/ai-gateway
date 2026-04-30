import time

import pytest
from kiro.usage.usage_cache import UsageCache, UsageEntry


class TestUsageCache:
    """Tests for kiro/usage/usage_cache.py"""

    def setup_method(self):
        self.cache = UsageCache()
        self.cache._cache = {
            1: UsageEntry(key_id=1, current_usage=100, usage_limit=1000, is_active=True),
            2: UsageEntry(key_id=2, current_usage=990, usage_limit=1000, is_active=True),
            3: UsageEntry(key_id=3, current_usage=500, usage_limit=1000, is_active=False),
            4: UsageEntry(key_id=4, current_usage=0, usage_limit=0, is_active=True),
        }

    def test_get_existing_key(self):
        entry = self.cache.get(1)
        assert entry is not None
        assert entry.current_usage == 100
        assert entry.usage_limit == 1000

    def test_get_nonexistent_key(self):
        assert self.cache.get(999) is None

    @pytest.mark.asyncio
    async def test_increment(self):
        await self.cache.increment(1, 5)
        assert self.cache.get(1).current_usage == 105

    @pytest.mark.asyncio
    async def test_increment_nonexistent_key_no_error(self):
        await self.cache.increment(999, 1)  # should not raise

    @pytest.mark.asyncio
    async def test_refresh_limits(self):
        await self.cache.refresh_limits({1: (2000, 200, None)})
        entry = self.cache.get(1)
        assert entry.usage_limit == 2000
        assert entry.current_usage == 200

    @pytest.mark.asyncio
    async def test_refresh_limits_stores_next_reset_at(self):
        future = time.time() + 3600
        await self.cache.refresh_limits({1: (2000, 200, future)})
        assert self.cache._cache[1].next_reset_at == future

    def test_get_resets_usage_after_next_reset_at(self):
        self.cache._cache[1].next_reset_at = time.time() - 1  # already past
        entry = self.cache.get(1)
        assert entry.current_usage == 0
        assert entry.next_reset_at is None

    def test_get_does_not_reset_before_next_reset_at(self):
        self.cache._cache[1].next_reset_at = time.time() + 3600
        entry = self.cache.get(1)
        assert entry.current_usage == 100  # unchanged

    @pytest.mark.asyncio
    async def test_increment_resets_before_adding(self):
        self.cache._cache[1].next_reset_at = time.time() - 1
        await self.cache.increment(1, 50)
        assert self.cache._cache[1].current_usage == 50  # reset to 0 then +50

    def test_get_available_keys_excludes_inactive(self):
        available = self.cache.get_available_keys()
        assert 3 not in available  # inactive

    def test_get_available_keys_excludes_zero_limit(self):
        available = self.cache.get_available_keys()
        assert 4 not in available  # zero limit

    def test_get_available_keys_excludes_near_quota(self):
        available = self.cache.get_available_keys()
        assert 2 not in available  # 990/1000 = 99% used, only 1% remaining

    def test_get_available_keys_includes_healthy(self):
        available = self.cache.get_available_keys()
        assert 1 in available  # 100/1000 = 10% used, 90% remaining

    def test_get_available_keys_excludes_specified_key(self):
        available = self.cache.get_available_keys(exclude_key_id=1)
        assert 1 not in available

    def test_get_available_keys_resets_expired_entry(self):
        # key 2 is near quota but its period has reset — should become available
        self.cache._cache[2].next_reset_at = time.time() - 1
        available = self.cache.get_available_keys()
        assert 2 in available

    def test_set_key_active(self):
        self.cache.set_key_active(3, True)
        assert self.cache.get(3).is_active is True
        available = self.cache.get_available_keys()
        assert 3 in available

    def test_set_key_active_nonexistent_no_error(self):
        self.cache.set_key_active(999, True)  # should not raise
