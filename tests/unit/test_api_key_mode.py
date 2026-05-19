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

from kiro.usage.token_cache import token_cache


@pytest.fixture(autouse=True)
def _clear_token_cache():
    token_cache.clear_sync()
    yield
    token_cache.clear_sync()

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
        adapter = ApiKeyAuthAdapter("tok")
        assert adapter.auth_type == "api_key"

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


# ===========================================================================
# _resolve_gateway_key
# ===========================================================================

class TestResolveGatewayKey:
    @pytest.mark.asyncio
    async def test_non_gateway_prefix_returns_none(self):
        from kiro.api_key_mode import _resolve_gateway_key
        result = await _resolve_gateway_key("sk-proj-someregularkey")
        assert result is None

    @pytest.mark.asyncio
    async def test_old_aigw_prefix_returns_none(self):
        from kiro.api_key_mode import _resolve_gateway_key
        result = await _resolve_gateway_key("aigw_someoldkey")
        assert result is None

    @pytest.mark.asyncio
    async def test_iziaigw_prefix_without_db_returns_none(self):
        from kiro.api_key_mode import _resolve_gateway_key
        with patch("kiro.api_key_mode.is_db_configured", return_value=False):
            result = await _resolve_gateway_key("iziaigw_somekey")
        assert result is None

    @pytest.mark.asyncio
    async def test_iziaigw_prefix_with_inactive_key_returns_none(self):
        from kiro.api_key_mode import _resolve_gateway_key
        mock_gk = MagicMock()
        mock_gk.is_active = False

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        with patch("kiro.api_key_mode.is_db_configured", return_value=True), \
             patch("kiro.db.engine.async_session_factory", return_value=mock_session), \
             patch("kiro.db.repositories.get_gateway_key_by_hash", new_callable=AsyncMock, return_value=mock_gk), \
             patch("kiro.usage.usage_cache.usage_cache"):
            result = await _resolve_gateway_key("iziaigw_testkey123")
        assert result is None

    @pytest.mark.asyncio
    async def test_iziaigw_prefix_with_no_available_kiro_keys_returns_none(self):
        from kiro.api_key_mode import _resolve_gateway_key
        mock_gk = MagicMock()
        mock_gk.is_active = True
        mock_gk.id = 7

        mock_session = AsyncMock()
        mock_cache = MagicMock()
        mock_cache.get_available_keys.return_value = []

        with patch("kiro.api_key_mode.is_db_configured", return_value=True), \
             patch("kiro.db.engine.async_session_factory", return_value=mock_session), \
             patch("kiro.db.repositories.get_gateway_key_by_hash", new_callable=AsyncMock, return_value=mock_gk), \
             patch("kiro.usage.usage_cache.usage_cache", mock_cache):
            result = await _resolve_gateway_key("iziaigw_testkey123")
        assert result is None

    @pytest.mark.asyncio
    async def test_iziaigw_resolves_to_best_kiro_key(self):
        from kiro.api_key_mode import _resolve_gateway_key
        mock_gk = MagicMock()
        mock_gk.is_active = True
        mock_gk.id = 7

        mock_entry_low = MagicMock()
        mock_entry_low.usage_limit = 1000
        mock_entry_low.current_usage = 900  # 100 remaining
        mock_entry_low.is_system = False

        mock_entry_high = MagicMock()
        mock_entry_high.usage_limit = 1000
        mock_entry_high.current_usage = 100  # 900 remaining — best
        mock_entry_high.is_system = False

        mock_cache = MagicMock()
        mock_cache.get_available_keys.return_value = [1, 2]
        mock_cache.get.side_effect = lambda kid: mock_entry_low if kid == 1 else mock_entry_high

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = "encrypted_key"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        with patch("kiro.api_key_mode.is_db_configured", return_value=True), \
             patch("kiro.db.engine.async_session_factory", return_value=mock_session), \
             patch("kiro.db.repositories.get_gateway_key_by_hash", new_callable=AsyncMock, return_value=mock_gk), \
             patch("kiro.db.repositories.decrypt_api_key", return_value="raw_kiro_key_abc"), \
             patch("kiro.usage.usage_cache.usage_cache", mock_cache):
            result = await _resolve_gateway_key("iziaigw_testkey123")

        assert result is not None
        raw_key, kiro_key_id, gateway_key_id = result
        assert raw_key == "raw_kiro_key_abc"
        assert kiro_key_id == 2  # key 2 has most remaining quota
        assert gateway_key_id == 7


# ===========================================================================
# _resolve_key_id
# ===========================================================================

class TestResolveKeyId:
    @pytest.mark.asyncio
    async def test_returns_none_when_db_not_configured(self):
        from kiro.api_key_mode import _resolve_key_id
        with patch("kiro.api_key_mode.is_db_configured", return_value=False):
            result = await _resolve_key_id("sk-proj-somekey")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_key_id_on_success(self):
        # Existing key found in DB
        from kiro.api_key_mode import _resolve_key_id
        mock_api_key = MagicMock()
        mock_api_key.id = 42

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("kiro.api_key_mode.is_db_configured", return_value=True), \
             patch("kiro.db.engine.async_session_factory", return_value=mock_session), \
             patch("kiro.db.repositories.get_api_key_by_hash", new_callable=AsyncMock, return_value=mock_api_key):
            result = await _resolve_key_id("sk-proj-somekey")
        assert result == 42

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_key(self):
        # Key not in DB — returns None, does NOT create
        from kiro.api_key_mode import _resolve_key_id

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("kiro.api_key_mode.is_db_configured", return_value=True), \
             patch("kiro.db.engine.async_session_factory", return_value=mock_session), \
             patch("kiro.db.repositories.get_api_key_by_hash", new_callable=AsyncMock, return_value=None):
            result = await _resolve_key_id("sk-proj-newkey")
        assert result is None

    @pytest.mark.asyncio
    async def test_syncs_new_key_on_first_seen(self):
        # _persist_new_key: new key gets created and synced
        from kiro.api_key_mode import _persist_new_key
        mock_api_key = MagicMock()
        mock_api_key.id = 99

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("kiro.api_key_mode.is_db_configured", return_value=True), \
             patch("kiro.db.engine.async_session_factory", return_value=mock_session), \
             patch("kiro.db.repositories.get_or_create_api_key", new_callable=AsyncMock, return_value=(mock_api_key, True)), \
             patch("kiro.api_key_mode.asyncio.ensure_future") as mock_future, \
             patch("kiro.api_key_mode._sync_new_key", new_callable=AsyncMock):
            await _persist_new_key("sk-proj-newkey")
        mock_future.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_returns_none_on_exception(self):
        from kiro.api_key_mode import _resolve_key_id

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("kiro.api_key_mode.is_db_configured", return_value=True), \
             patch("kiro.db.engine.async_session_factory", return_value=mock_session), \
             patch("kiro.db.repositories.get_api_key_by_hash", new_callable=AsyncMock, side_effect=Exception("DB error")):
            result = await _resolve_key_id("sk-proj-somekey")
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_cache_on_subsequent_calls(self):
        """First call should populate cache; second call should not call DB."""
        from kiro.api_key_mode import _resolve_key_id
        mock_api_key = MagicMock()
        mock_api_key.id = 123

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        get_by_hash = AsyncMock(return_value=mock_api_key)

        with patch("kiro.api_key_mode.is_db_configured", return_value=True), \
             patch("kiro.db.engine.async_session_factory", return_value=mock_session), \
             patch("kiro.db.repositories.get_api_key_by_hash", new=get_by_hash):
            r1 = await _resolve_key_id("sk-proj-somekey")
            r2 = await _resolve_key_id("sk-proj-somekey")

        assert r1 == 123
        assert r2 == 123
        assert get_by_hash.call_count == 1
