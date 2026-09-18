# -*- coding: utf-8 -*-

"""
Unit tests for kiro/api_key_mode.py.

Covers:
- extract_bearer_token
- get_api_key_from_request
- build_api_key_headers
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from kiro.usage.token_cache import token_cache


@pytest.fixture(autouse=True)
def _clear_token_cache():
    token_cache.clear_sync()
    yield
    token_cache.clear_sync()

from fastapi import HTTPException

from kiro.api_key_mode import (
    build_api_key_headers,
    extract_bearer_token,
    get_api_key_from_request,
)


# ===========================================================================
# extract_bearer_token
# ===========================================================================

class TestExtractBearerToken:
    def test_valid_bearer_returns_token(self):
        assert extract_bearer_token("Bearer my-secret-key") == "my-secret-key"

    def test_none_returns_none(self):
        assert extract_bearer_token(None) is None

    def test_empty_string_returns_none(self):
        assert extract_bearer_token("") is None

    def test_no_bearer_prefix_returns_none(self):
        assert extract_bearer_token("my-secret-key") is None

    def test_lowercase_bearer_returns_none(self):
        assert extract_bearer_token("bearer my-secret-key") is None

    def test_bearer_with_spaces_in_token(self):
        # Token itself may contain spaces (edge case)
        result = extract_bearer_token("Bearer tok en")
        assert result == "tok en"


# ===========================================================================
# get_api_key_from_request
# ===========================================================================

class TestGetApiKeyFromRequest:
    def _make_request(self, auth_header=None):
        req = Mock()
        req.headers = {}
        if auth_header is not None:
            req.headers = {"Authorization": auth_header}
        return req

    def test_valid_bearer_returns_token(self):
        req = self._make_request("Bearer kiro-api-key-123")
        token = get_api_key_from_request(req)
        assert token == "kiro-api-key-123"

    def test_missing_header_raises_401(self):
        req = self._make_request()
        with pytest.raises(HTTPException) as exc_info:
            get_api_key_from_request(req)
        assert exc_info.value.status_code == 401

    def test_non_bearer_header_raises_401(self):
        req = self._make_request("Basic dXNlcjpwYXNz")
        with pytest.raises(HTTPException) as exc_info:
            get_api_key_from_request(req)
        assert exc_info.value.status_code == 401


# ===========================================================================
# build_api_key_headers
# ===========================================================================

class TestBuildApiKeyHeaders:
    def test_authorization_header_contains_token(self):
        headers = build_api_key_headers("my-token")
        assert headers["Authorization"] == "Bearer my-token"

    def test_content_type_is_json(self):
        headers = build_api_key_headers("tok")
        assert headers["Content-Type"] == "application/json"

    def test_required_kiro_headers_present(self):
        headers = build_api_key_headers("tok")
        assert "User-Agent" in headers
        assert "x-amz-user-agent" in headers
        assert "x-amzn-codewhisperer-optout" in headers
        assert "amz-sdk-invocation-id" in headers

    def test_invocation_id_is_unique(self):
        h1 = build_api_key_headers("tok")
        h2 = build_api_key_headers("tok")
        assert h1["amz-sdk-invocation-id"] != h2["amz-sdk-invocation-id"]

