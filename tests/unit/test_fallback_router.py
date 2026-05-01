import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from kiro.usage.fallback import FallbackRouter, NoAvailableKeyError
from kiro.usage.usage_cache import UsageCache, UsageEntry


class TestFallbackRouter:
    """Tests for kiro/usage/fallback.py"""

    def setup_method(self):
        self.router = FallbackRouter()
        self.cache = UsageCache()
        self.cache._cache = {
            1: UsageEntry(key_id=1, current_usage=995, usage_limit=1000, is_active=True),  # near quota
            2: UsageEntry(key_id=2, current_usage=100, usage_limit=1000, is_active=True),   # healthy
            3: UsageEntry(key_id=3, current_usage=50, usage_limit=1000, is_active=True),    # healthy
            4: UsageEntry(key_id=4, current_usage=0, usage_limit=1000, is_active=False),    # inactive
        }

    @pytest.mark.asyncio
    async def test_pre_check_returns_none_when_sharing_disabled(self):
        self.router._sharing_enabled = False
        result = await self.router.pre_check(1)
        assert result is None

    @pytest.mark.asyncio
    async def test_pre_check_returns_none_when_key_has_quota(self):
        self.router._sharing_enabled = True
        with patch("kiro.usage.fallback.usage_cache", self.cache):
            result = await self.router.pre_check(2)  # 90% remaining
            assert result is None

    @pytest.mark.asyncio
    async def test_pre_check_triggers_fallback_when_near_quota(self):
        self.router._sharing_enabled = True
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "encrypted_key_data"

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_ctx)

        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("kiro.usage.fallback.usage_cache", self.cache), \
             patch("kiro.usage.usage_cache.usage_cache", self.cache), \
             patch("kiro.db.engine.async_session_factory", mock_factory), \
             patch("kiro.db.repositories.decrypt_api_key", return_value="raw_key_2"):
            result = await self.router.pre_check(1)  # 0.5% remaining
            assert result is not None
            new_key_id, raw_key = result
            assert new_key_id in [2, 3]  # should pick a healthy key
            assert raw_key == "raw_key_2"

    @pytest.mark.asyncio
    async def test_post_check_returns_none_when_sharing_disabled(self):
        self.router._sharing_enabled = False
        result = await self.router.post_check(1)
        assert result is None

    def test_update_sharing_config(self):
        self.router.update_sharing_config(True)
        assert self.router._sharing_enabled is True
        self.router.update_sharing_config(False)
        assert self.router._sharing_enabled is False

    @pytest.mark.asyncio
    async def test_pick_fallback_raises_when_no_keys_available(self):
        # All keys either inactive or near quota
        self.cache._cache = {
            1: UsageEntry(key_id=1, current_usage=999, usage_limit=1000, is_active=True),
        }
        with patch("kiro.usage.fallback.usage_cache", self.cache):
            with pytest.raises(NoAvailableKeyError):
                await self.router._pick_fallback_key(exclude_key_id=1)
