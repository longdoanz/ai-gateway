import pytest
from unittest.mock import AsyncMock, patch
from kiro.usage.tracker import extract_credits_from_response, track_usage


class TestExtractCredits:
    """Tests for kiro/usage/tracker.py extract_credits_from_response"""

    def test_extract_from_credits_used_field(self):
        assert extract_credits_from_response({"creditsUsed": 5}) == 5

    def test_extract_from_credits_used_snake_case(self):
        assert extract_credits_from_response({"credits_used": 10}) == 10

    def test_extract_from_usage_breakdown_list(self):
        data = {
            "usageBreakdownList": [
                {"resourceType": "CREDIT", "currentUsage": 1154}
            ]
        }
        assert extract_credits_from_response(data) == 1154

    def test_extract_from_bytes(self):
        import json
        data = json.dumps({"creditsUsed": 7}).encode()
        assert extract_credits_from_response(data) == 7

    def test_extract_from_invalid_bytes(self):
        assert extract_credits_from_response(b"not json") is None

    def test_extract_from_none(self):
        assert extract_credits_from_response(None) is None

    def test_extract_from_empty_dict(self):
        assert extract_credits_from_response({}) is None

    def test_extract_from_empty_breakdown(self):
        assert extract_credits_from_response({"usageBreakdownList": []}) is None

    def test_extract_from_real_kiro_response(self):
        """Test with actual Kiro API response structure from getUsageLimits"""
        data = {
            "usageBreakdownList": [{
                "currentUsage": 1154,
                "currentUsageWithPrecision": 1154.26,
                "usageLimit": 2000,
                "resourceType": "CREDIT",
                "unit": "INVOCATIONS",
            }]
        }
        assert extract_credits_from_response(data) == 1154


class TestTrackUsage:
    @pytest.mark.asyncio
    async def test_skip_when_credits_zero(self):
        with patch("kiro.usage.tracker.async_session_factory") as mock_factory:
            await track_usage(key_id=1, credits_used=0)
            mock_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_when_credits_zero_does_not_update_cache(self):
        with patch("kiro.usage.tracker.usage_cache") as mock_cache:
            with patch("kiro.usage.tracker.async_session_factory"):
                await track_usage(key_id=1, credits_used=0)
                mock_cache.increment.assert_not_called()

    @pytest.mark.asyncio
    async def test_proceeds_when_credits_none(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("kiro.usage.tracker.async_session_factory", return_value=mock_session):
            with patch("kiro.usage.tracker.increment_usage", new_callable=AsyncMock) as mock_inc:
                with patch("kiro.usage.tracker.usage_cache") as mock_cache:
                    mock_cache.increment = AsyncMock()
                    await track_usage(key_id=1, credits_used=None)
                    assert mock_inc.call_args[0][3] == 1  # amount defaults to 1

    @pytest.mark.asyncio
    async def test_proceeds_when_credits_positive(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("kiro.usage.tracker.async_session_factory", return_value=mock_session):
            with patch("kiro.usage.tracker.increment_usage", new_callable=AsyncMock) as mock_inc:
                with patch("kiro.usage.tracker.usage_cache") as mock_cache:
                    mock_cache.increment = AsyncMock()
                    await track_usage(key_id=2, credits_used=42)
                    assert mock_inc.call_args[0][3] == 42
