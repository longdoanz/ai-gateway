# -*- coding: utf-8 -*-

"""
Unit tests for kiro/api_key_mode.py.

Covers:
- extract_bearer_token
- get_api_key_from_request
- build_api_key_headers
- ApiKeyModeClient (init, retry, 403 handling, close)
- ApiKeyAuthAdapter (properties, get_access_token, force_refresh)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
from fastapi import HTTPException

from kiro.api_key_mode import (
    ApiKeyAuthAdapter,
    ApiKeyModeClient,
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


# ===========================================================================
# ApiKeyModeClient
# ===========================================================================

class TestApiKeyModeClientInit:
    def test_stores_token(self):
        client = ApiKeyModeClient("my-token")
        assert client.token == "my-token"

    def test_owns_client_when_no_shared(self):
        client = ApiKeyModeClient("tok")
        assert client._owns_client is True
        assert client.client is None

    def test_uses_shared_client(self):
        shared = MagicMock()
        client = ApiKeyModeClient("tok", shared_client=shared)
        assert client._owns_client is False
        assert client.client is shared


class TestApiKeyModeClientClose:
    @pytest.mark.asyncio
    async def test_close_owned_client(self):
        client = ApiKeyModeClient("tok")
        mock_http = AsyncMock()
        mock_http.is_closed = False
        client.client = mock_http
        await client.close()
        mock_http.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_does_not_close_shared_client(self):
        shared = AsyncMock()
        shared.is_closed = False
        client = ApiKeyModeClient("tok", shared_client=shared)
        await client.close()
        shared.aclose.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_already_closed_client_is_noop(self):
        client = ApiKeyModeClient("tok")
        mock_http = AsyncMock()
        mock_http.is_closed = True
        client.client = mock_http
        await client.close()
        mock_http.aclose.assert_not_awaited()


class TestApiKeyModeClientRequestWithRetry:
    def _make_response(self, status_code: int) -> Mock:
        resp = Mock(spec=httpx.Response)
        resp.status_code = status_code
        return resp

    @pytest.mark.asyncio
    async def test_200_returns_response(self):
        client = ApiKeyModeClient("tok")
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.request = AsyncMock(return_value=self._make_response(200))
        client.client = mock_http

        resp = await client.request_with_retry("POST", "http://example.com", {})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_403_raises_401_http_exception(self):
        client = ApiKeyModeClient("tok")
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.request = AsyncMock(return_value=self._make_response(403))
        client.client = mock_http

        with pytest.raises(HTTPException) as exc_info:
            await client.request_with_retry("POST", "http://example.com", {})
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_non_200_non_403_returned_as_is(self):
        client = ApiKeyModeClient("tok")
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.request = AsyncMock(return_value=self._make_response(400))
        client.client = mock_http

        resp = await client.request_with_retry("POST", "http://example.com", {})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_429_retries_and_eventually_succeeds(self):
        client = ApiKeyModeClient("tok")
        mock_http = AsyncMock()
        mock_http.is_closed = False
        # First call returns 429, second returns 200
        mock_http.request = AsyncMock(side_effect=[
            self._make_response(429),
            self._make_response(200),
        ])
        client.client = mock_http

        with patch("kiro.api_key_mode.asyncio.sleep", new_callable=AsyncMock):
            resp = await client.request_with_retry("POST", "http://example.com", {})
        assert resp.status_code == 200
        assert mock_http.request.call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_raises_504_after_retries(self):
        client = ApiKeyModeClient("tok")
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.request = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        client.client = mock_http

        with patch("kiro.api_key_mode.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await client.request_with_retry("POST", "http://example.com", {})
        assert exc_info.value.status_code == 504

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with ApiKeyModeClient("tok") as client:
            assert isinstance(client, ApiKeyModeClient)


# ===========================================================================
# ApiKeyAuthAdapter
# ===========================================================================

class TestApiKeyAuthAdapter:
    def test_api_host_uses_region(self):
        adapter = ApiKeyAuthAdapter("tok", region="us-east-1")
        assert "us-east-1" in adapter.api_host

    def test_q_host_uses_region(self):
        adapter = ApiKeyAuthAdapter("tok", region="us-east-1")
        assert "us-east-1" in adapter.q_host

    def test_profile_arn_is_none(self):
        adapter = ApiKeyAuthAdapter("tok")
        assert adapter.profile_arn is None

    def test_auth_type_is_not_kiro_desktop(self):
        from kiro.auth import AuthType
        adapter = ApiKeyAuthAdapter("tok")
        assert adapter.auth_type != AuthType.KIRO_DESKTOP

    def test_fingerprint_is_string(self):
        adapter = ApiKeyAuthAdapter("tok")
        assert isinstance(adapter.fingerprint, str)
        assert len(adapter.fingerprint) > 0

    def test_region_property(self):
        adapter = ApiKeyAuthAdapter("tok", region="eu-west-1")
        assert adapter.region == "eu-west-1"

    @pytest.mark.asyncio
    async def test_get_access_token_returns_token(self):
        adapter = ApiKeyAuthAdapter("my-kiro-key")
        token = await adapter.get_access_token()
        assert token == "my-kiro-key"

    @pytest.mark.asyncio
    async def test_force_refresh_returns_token(self):
        adapter = ApiKeyAuthAdapter("my-kiro-key")
        token = await adapter.force_refresh()
        assert token == "my-kiro-key"

    def test_different_regions_produce_different_hosts(self):
        a1 = ApiKeyAuthAdapter("tok", region="us-east-1")
        a2 = ApiKeyAuthAdapter("tok", region="eu-west-1")
        assert a1.api_host != a2.api_host
        assert a1.q_host != a2.q_host
