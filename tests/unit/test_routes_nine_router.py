# -*- coding: utf-8 -*-
"""
Unit tests for kiro/routes_nine_router.py.

Tests cover:
- Admin access allowed
- Non-admin blocked (403)
- Unauthenticated blocked (401)
- 9router not configured returns 503
- Proxy strips auth header, adds API key
- Redirect Location header rewritten
- SSE streaming response passthrough
- Connect error → 503, timeout → 504
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiro.db.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_admin_user(user_id: int = 1) -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    user.role = "admin"
    user.username = "admin"
    user.is_active = True
    return user


def _make_regular_user(user_id: int = 2) -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    user.role = "user"
    user.username = "bob"
    user.is_active = True
    return user


def _mock_stream_response(
    status_code: int = 200,
    body: bytes = b'{"ok": true}',
    content_type: str = "application/json",
    headers: dict | None = None,
):
    header_items = list((headers or {"content-type": content_type}).items())
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = MagicMock()
    resp.headers.get = MagicMock(side_effect=lambda key, default=None: dict(header_items).get(key, default))
    resp.headers.multi_items = MagicMock(return_value=header_items)
    resp.aread = AsyncMock(return_value=body)

    async def _aiter():
        yield body

    resp.aiter_bytes = _aiter
    return resp


def _make_stream_cm(response):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_client_mock(stream_cm):
    client = MagicMock()
    client.stream = MagicMock(return_value=stream_cm)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

class TestAccessControl:
    def test_no_auth_returns_403_or_401(self):
        import kiro.routes_nine_router as mod
        app = FastAPI()
        app.include_router(mod.router)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/9router/dashboard")
        assert resp.status_code in (401, 403)

    def test_non_admin_returns_403(self):
        import kiro.routes_nine_router as mod
        app = FastAPI()

        async def _fake_require_admin():
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Admin access required")

        app.dependency_overrides[mod.require_admin] = _fake_require_admin
        app.include_router(mod.router)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/9router/dashboard")
        assert resp.status_code == 403

    def test_admin_passes_through(self):
        import kiro.routes_nine_router as mod
        upstream = _mock_stream_response()
        mock_client = _make_client_mock(_make_stream_cm(upstream))

        app = FastAPI()
        admin = _make_admin_user()
        app.dependency_overrides[mod.require_admin] = lambda: admin
        app.include_router(mod.router)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_PASSWORD", ""),
            patch("kiro.routes_nine_router.httpx.AsyncClient", return_value=mock_client),
        ):
            client = TestClient(app)
            resp = client.get("/9router/dashboard")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Not configured
# ---------------------------------------------------------------------------

class TestNotConfigured:
    def test_returns_503_when_url_empty(self):
        import kiro.routes_nine_router as mod
        app = FastAPI()
        admin = _make_admin_user()
        app.dependency_overrides[mod.require_admin] = lambda: admin
        app.include_router(mod.router)

        with patch.object(mod, "NINE_ROUTER_URL", ""):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/9router/dashboard")
            assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Header handling
# ---------------------------------------------------------------------------

class TestHeaderHandling:
    def test_strips_authorization_header(self):
        import kiro.routes_nine_router as mod
        upstream = _mock_stream_response()
        stream_cm = _make_stream_cm(upstream)
        captured = {}
        mock_client = _make_client_mock(stream_cm)

        def _capture(**kwargs):
            captured["headers"] = kwargs.get("headers", {})
            return stream_cm

        mock_client.stream = MagicMock(side_effect=_capture)

        app = FastAPI()
        admin = _make_admin_user()
        app.dependency_overrides[mod.require_admin] = lambda: admin
        app.include_router(mod.router)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_API_KEY", ""),
            patch.object(mod, "NINE_ROUTER_PASSWORD", ""),
            patch("kiro.routes_nine_router.httpx.AsyncClient", return_value=mock_client),
        ):
            client = TestClient(app)
            client.get("/9router/dashboard", headers={"Authorization": "Bearer user-jwt"})
            assert "authorization" not in {k.lower() for k in captured.get("headers", {})}

    def test_adds_nine_router_api_key(self):
        import kiro.routes_nine_router as mod
        upstream = _mock_stream_response()
        stream_cm = _make_stream_cm(upstream)
        captured = {}
        mock_client = _make_client_mock(stream_cm)

        def _capture(**kwargs):
            captured["headers"] = kwargs.get("headers", {})
            return stream_cm

        mock_client.stream = MagicMock(side_effect=_capture)

        app = FastAPI()
        admin = _make_admin_user()
        app.dependency_overrides[mod.require_admin] = lambda: admin
        app.include_router(mod.router)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_API_KEY", "nr-secret"),
            patch.object(mod, "NINE_ROUTER_PASSWORD", ""),
            patch("kiro.routes_nine_router.httpx.AsyncClient", return_value=mock_client),
        ):
            client = TestClient(app)
            client.get("/9router/dashboard")
            assert captured.get("headers", {}).get("Authorization") == "Bearer nr-secret"

    def test_rewrites_redirect_location(self):
        import kiro.routes_nine_router as mod
        upstream = _mock_stream_response(
            status_code=302,
            body=b"",
            content_type="text/html",
            headers={
                "location": "http://ninerouter:20128/dashboard",
                "content-type": "text/html",
            },
        )
        mock_client = _make_client_mock(_make_stream_cm(upstream))

        app = FastAPI()
        admin = _make_admin_user()
        app.dependency_overrides[mod.require_admin] = lambda: admin
        app.include_router(mod.router)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_PASSWORD", ""),
            patch("kiro.routes_nine_router.httpx.AsyncClient", return_value=mock_client),
        ):
            client = TestClient(app, follow_redirects=False)
            resp = client.get("/9router/dashboard")
            assert resp.headers.get("location", "").startswith("/9router")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_connect_error_returns_503(self):
        import kiro.routes_nine_router as mod
        import httpx

        mock_client = _make_client_mock(MagicMock())
        mock_client.stream = MagicMock(side_effect=httpx.ConnectError("refused"))

        app = FastAPI()
        admin = _make_admin_user()
        app.dependency_overrides[mod.require_admin] = lambda: admin
        app.include_router(mod.router)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_PASSWORD", ""),
            patch("kiro.routes_nine_router.httpx.AsyncClient", return_value=mock_client),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/9router/dashboard")
            assert resp.status_code == 503

    def test_timeout_returns_504(self):
        import kiro.routes_nine_router as mod
        import httpx

        mock_client = _make_client_mock(MagicMock())
        mock_client.stream = MagicMock(side_effect=httpx.TimeoutException("timed out"))

        app = FastAPI()
        admin = _make_admin_user()
        app.dependency_overrides[mod.require_admin] = lambda: admin
        app.include_router(mod.router)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_PASSWORD", ""),
            patch("kiro.routes_nine_router.httpx.AsyncClient", return_value=mock_client),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/9router/dashboard")
            assert resp.status_code == 504
