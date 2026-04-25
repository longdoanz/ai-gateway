import pytest
from kiro.usage.tracker import extract_credits_from_response


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
