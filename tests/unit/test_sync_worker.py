import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from aigw.usage.sync_worker import sync_usage_limits

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
async def test_sync_usage_limits_syncs_every_active_key():
    key1 = MagicMock(id=1, key_encrypted="enc1")
    key2 = MagicMock(id=2, key_encrypted="enc2")
    key3 = MagicMock(id=3, key_encrypted="enc3")

    mock_session = AsyncMock()
    mock_session.execute.return_value = _FakeResult([key1, key2, key3])

    with patch("aigw.usage.sync_worker.async_session_factory") as mock_factory, \
         patch("aigw.usage.sync_worker.decrypt_api_key", return_value="raw_key"), \
         patch("aigw.api_key_mode.get_usage_limits") as mock_get_limits, \
         patch("aigw.usage.sync_worker.upsert_usage_limits") as mock_upsert_limits, \
         patch("aigw.usage.sync_worker.update_api_key") as mock_update_key:

        mock_factory.return_value.__aenter__.return_value = mock_session

        mock_get_limits.return_value = {
            "usageBreakdownList": [{"resourceType": "CREDIT", "usageLimit": 1000, "currentUsage": 500}],
        }

        await sync_usage_limits([1, 2, 3])

        # Every active key is synced independently, no dedup/grouping.
        assert mock_get_limits.call_count == 3

        # One session for the initial fetch, plus one per synced key.
        assert mock_factory.return_value.__aenter__.call_count == 4

        assert mock_upsert_limits.call_count == 3
