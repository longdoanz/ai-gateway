import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
import httpx
from kiro.usage.fallback import FallbackRouter
from kiro.usage.usage_cache import UsageCache, UsageEntry
from kiro.api_key_mode import ApiKeyModeClient

class TestSystemKeysLogic:
    """Tests for system keys prioritization and proxy bypass."""

    def setup_method(self):
        self.router = FallbackRouter()
        self.cache = UsageCache()
        # Key 1: User key, healthy
        # Key 2: System key, healthy
        # Key 3: System key, healthy (better usage)
        self.cache._cache = {
            1: UsageEntry(key_id=1, current_usage=100, usage_limit=1000, is_active=True, is_system=False),
            2: UsageEntry(key_id=2, current_usage=200, usage_limit=1000, is_active=True, is_system=True),
            3: UsageEntry(key_id=3, current_usage=50, usage_limit=1000, is_active=True, is_system=True),
        }

    @pytest.mark.asyncio
    async def test_fallback_prioritizes_system_keys(self):
        """Verify that system keys are picked before user keys in fallback."""
        with patch("kiro.usage.fallback.usage_cache", self.cache), \
             patch("kiro.usage.usage_cache.usage_cache", self.cache), \
             patch("kiro.usage.fallback.sticky_binder.pick_and_decrypt", AsyncMock(side_effect=lambda eid, pool: (pool[0], "raw_key"))):
            
            picked_id, _ = await self.router._pick_fallback_key(exclude_key_id=0)
            assert picked_id in [2, 3]

    @pytest.mark.asyncio
    async def test_fallback_falls_back_to_user_keys_if_no_system_keys(self):
        """Verify that user keys are used if no system keys are available."""
        self.cache._cache = {
            1: UsageEntry(key_id=1, current_usage=100, usage_limit=1000, is_active=True, is_system=False),
            2: UsageEntry(key_id=2, current_usage=1000, usage_limit=1000, is_active=True, is_system=True), # Exhausted
        }
        with patch("kiro.usage.fallback.usage_cache", self.cache), \
             patch("kiro.usage.usage_cache.usage_cache", self.cache), \
             patch("kiro.usage.fallback.sticky_binder.pick_and_decrypt", AsyncMock(side_effect=lambda eid, pool: (pool[0], "raw_key"))):
            
            picked_id, _ = await self.router._pick_fallback_key(exclude_key_id=0)
            assert picked_id == 1

    @pytest.mark.asyncio
    async def test_api_key_mode_client_trust_env_toggle(self):
        """Verify that trust_env is set correctly based on use_proxy flag."""
        # Key 1: use_proxy=True (default)
        # Key 2: use_proxy=False
        self.cache._cache = {
            1: UsageEntry(key_id=1, current_usage=0, usage_limit=1000, is_active=True, use_proxy=True),
            2: UsageEntry(key_id=2, current_usage=0, usage_limit=1000, is_active=True, use_proxy=False),
        }
        
        with patch("kiro.usage.usage_cache.usage_cache", self.cache), \
             patch("httpx.AsyncClient") as mock_client:
            
            # Case 1: use_proxy=True
            client1 = ApiKeyModeClient(token="token1", key_id=1)
            await client1._get_client()
            mock_client.assert_called_with(timeout=ANY, follow_redirects=True, trust_env=True)
            
            mock_client.reset_mock()
            
            # Case 2: use_proxy=False
            client2 = ApiKeyModeClient(token="token2", key_id=2)
            await client2._get_client()
            mock_client.assert_called_with(timeout=ANY, follow_redirects=True, trust_env=False)

    @pytest.mark.asyncio
    async def test_api_key_mode_client_defaults_to_trust_env_true(self):
        """Verify it defaults to True if key_id is missing or entry not found."""
        with patch("kiro.usage.usage_cache.usage_cache", self.cache), \
             patch("httpx.AsyncClient") as mock_client:
            
            client = ApiKeyModeClient(token="token_no_id", key_id=None)
            await client._get_client()
            mock_client.assert_called_with(timeout=ANY, follow_redirects=True, trust_env=True)
