import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from kiro.usage.sync_worker import sync_usage_limits, _snapshot_daily_credits

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows
    def all(self):
        return self._rows
    def scalars(self):
        return self
    def __iter__(self):
        return iter(self._rows)

@pytest.mark.asyncio
async def test_sync_usage_limits_optimizes_calls():
    # Mock data
    key1 = MagicMock(id=1, kiro_user_id="user1", key_encrypted="enc1")
    key2 = MagicMock(id=2, kiro_user_id="user1", key_encrypted="enc2")
    key3 = MagicMock(id=3, kiro_user_id=None, key_encrypted="enc3")
    keys = [key1, key2, key3]

    mock_session = AsyncMock()
    mock_session.execute.return_value = _FakeResult([key1, key2, key3])
    
    # Mocking external calls
    with patch("kiro.usage.sync_worker.async_session_factory") as mock_factory, \
         patch("kiro.usage.sync_worker.decrypt_api_key", return_value="raw_key"), \
         patch("kiro.api_key_mode.get_usage_limits") as mock_get_limits, \
         patch("kiro.usage.sync_worker.upsert_usage_limits") as mock_upsert_limits, \
         patch("kiro.usage.sync_worker.upsert_kiro_user_mappings") as mock_upsert_mappings, \
         patch("kiro.usage.sync_worker.update_api_key") as mock_update_key, \
         patch("kiro.usage.sync_worker.merge_duplicate_keys_for_user") as mock_merge, \
         patch("kiro.usage.sync_worker._snapshot_daily_credits") as mock_snapshot:
        
        # Configure mock_factory to return a mock_session context manager
        mock_factory.return_value.__aenter__.return_value = mock_session
        
        mock_get_limits.return_value = {
            "usageBreakdownList": [{"resourceType": "CREDIT", "usageLimit": 1000, "currentUsage": 500}],
            "userInfo": {"userId": "user1"}
        }
        mock_merge.return_value = (1, [])

        # We need to simulate that the first session returns the keys
        # and subsequent sessions are used for sync.
        # But wait, sync_usage_limits first fetches keys in one session, 
        # then iterates and opens NEW sessions for each sync.
        
        await sync_usage_limits([1, 2, 3])

        # Verify optimization: 
        # key1 and key2 share "user1" -> only one API call (for key2, since it's newer/higher id)
        # key3 has None -> one API call
        # Total: 2 calls to get_usage_limits
        assert mock_get_limits.call_count == 2
        
        # Verify transaction isolation: 
        # One for initial fetch, plus one for each sync (2 syncs)
        # Total __aenter__ calls: 3
        assert mock_factory.return_value.__aenter__.call_count == 3

@pytest.mark.asyncio
async def test_snapshot_daily_credits_isolates_transactions():
    row1 = MagicMock(kiro_user_id="user1", current_usage=500)
    row2 = MagicMock(kiro_user_id="user2", current_usage=600)
    
    mock_session = AsyncMock()
    mock_session.execute.return_value = _FakeResult([row1, row2])

    with patch("kiro.usage.sync_worker.async_session_factory") as mock_factory, \
         patch("kiro.usage.sync_worker.upsert_daily_credit_snapshot") as mock_upsert:
        
        mock_factory.return_value.__aenter__.return_value = mock_session
        
        await _snapshot_daily_credits()
        
        # One for initial fetch, one for each user snapshot (2 users)
        # Total __aenter__ calls: 3
        assert mock_factory.return_value.__aenter__.call_count == 3
        assert mock_upsert.call_count == 2
