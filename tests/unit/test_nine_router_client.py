# -*- coding: utf-8 -*-
"""
Unit tests for kiro/nine_router_client.py.

Tests cover:
- is_nine_router_enabled()
- forward_to_nine_router() — fallback triggered, not triggered, streaming passthrough
- Error handling: connect error, timeout, non-200 upstream, disabled
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.datastructures import Headers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_request(
    method: str = "POST",
    path: str = "/v1/chat/completions",
    query: str = "",
    headers: dict | None = None,
) -> MagicMock:
    req = MagicMock(spec=Request)
    req.method = method
    req.url.path = path
    req.url.query = query
    req.headers = Headers(headers or {"content-type": "application/json"})
    req.body = AsyncMock(return_value=b'{"model":"gpt-4","messages":[]}')
    return req


def _mock_stream_response(status_code: int = 200, chunks: list[bytes] | None = None, headers: dict | None = None):
    """Build an async context-manager mock that streams chunks."""
    chunks = chunks or [b"data: chunk1\n\n", b"data: [DONE]\n\n"]
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {"content-type": "text/event-stream"}

    async def _aiter():
        for c in chunks:
            yield c

    resp.aiter_bytes = _aiter

    async def _aread():
        return b"error body"

    resp.aread = _aread

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# is_nine_router_enabled
# ---------------------------------------------------------------------------

class TestIsNineRouterEnabled:
    def test_enabled_when_url_set(self):
        import kiro.nine_router_client as mod
        with patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"):
            assert mod.is_nine_router_enabled() is True

    def test_disabled_when_url_empty(self):
        import kiro.nine_router_client as mod
        with patch.object(mod, "NINE_ROUTER_URL", ""):
            assert mod.is_nine_router_enabled() is False


# ---------------------------------------------------------------------------
# forward_to_nine_router
# ---------------------------------------------------------------------------

class TestForwardToNineRouter:
    @pytest.mark.asyncio
    async def test_returns_503_when_not_configured(self):
        import kiro.nine_router_client as mod
        with patch.object(mod, "NINE_ROUTER_URL", ""):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, JSONResponse)
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_streams_response_on_success(self):
        import kiro.nine_router_client as mod
        stream_cm = _mock_stream_response(200)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=stream_cm)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, StreamingResponse)
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_adds_api_key_header_when_configured(self):
        import kiro.nine_router_client as mod
        stream_cm = _mock_stream_response(200)

        captured_headers = {}

        mock_client = MagicMock()

        def _capture_stream(**kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return stream_cm

        mock_client.stream = MagicMock(side_effect=_capture_stream)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_API_KEY", "secret-key"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            req = _mock_request()
            await mod.forward_to_nine_router(req, b"{}")
            assert captured_headers.get("Authorization") == "Bearer secret-key"

    @pytest.mark.asyncio
    async def test_strips_original_authorization_header(self):
        import kiro.nine_router_client as mod
        stream_cm = _mock_stream_response(200)
        captured_headers = {}

        mock_client = MagicMock()

        def _capture_stream(**kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return stream_cm

        mock_client.stream = MagicMock(side_effect=_capture_stream)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_API_KEY", ""),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            req = _mock_request(headers={"authorization": "Bearer gateway-user-token"})
            await mod.forward_to_nine_router(req, b"{}")
            assert "Authorization" not in captured_headers
            assert "authorization" not in captured_headers

    @pytest.mark.asyncio
    async def test_non_200_upstream_returns_json_error(self):
        import kiro.nine_router_client as mod
        stream_cm = _mock_stream_response(429)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=stream_cm)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, JSONResponse)
            assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_connect_error_returns_503(self):
        import kiro.nine_router_client as mod
        import httpx

        mock_client = MagicMock()
        mock_client.stream = MagicMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, JSONResponse)
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_timeout_returns_504(self):
        import kiro.nine_router_client as mod
        import httpx

        mock_client = MagicMock()
        mock_client.stream = MagicMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, JSONResponse)
            assert resp.status_code == 504

    @pytest.mark.asyncio
    async def test_correct_target_url_built(self):
        import kiro.nine_router_client as mod
        stream_cm = _mock_stream_response(200)
        captured_url = {}

        mock_client = MagicMock()

        def _capture(**kwargs):
            captured_url["url"] = kwargs.get("url", "")
            return stream_cm

        mock_client.stream = MagicMock(side_effect=_capture)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            req = _mock_request(path="/v1/chat/completions")
            await mod.forward_to_nine_router(req, b"{}")
            assert captured_url["url"] == "http://ninerouter:20128/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_query_string_forwarded(self):
        import kiro.nine_router_client as mod
        stream_cm = _mock_stream_response(200)
        captured_url = {}

        mock_client = MagicMock()

        def _capture(**kwargs):
            captured_url["url"] = kwargs.get("url", "")
            return stream_cm

        mock_client.stream = MagicMock(side_effect=_capture)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            req = _mock_request(path="/v1/models", query="foo=bar")
            await mod.forward_to_nine_router(req, b"")
            assert "foo=bar" in captured_url["url"]
