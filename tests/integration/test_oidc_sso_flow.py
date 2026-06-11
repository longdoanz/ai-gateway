# -*- coding: utf-8 -*-
"""
Integration tests for the OIDC SSO flow end-to-end.

Tests the full chain:
  login → /oauth/authorize (prompt=none) → code → /oauth/token → id_token → /oauth/jwks verify

Also covers:
  - Unauthenticated with prompt=none → error=login_required
  - Expired authorization code → 400
  - Wrong client_secret → 401
"""

import base64
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt


# ---------------------------------------------------------------------------
# Shared app fixture
# ---------------------------------------------------------------------------

def _build_app(user: object | None = None, client_secret: str = "integration-secret"):
    """Build a minimal app with OIDC routes and optional user session."""
    import importlib
    import os

    with patch.dict(
        os.environ,
        {
            "OIDC_CLIENT_SECRET": client_secret,
            "OIDC_REDIRECT_URI": "http://localhost:20128/api/auth/oidc/callback",
            "OIDC_ISSUER_URL": "http://localhost:18000",
        },
        clear=False,
    ):
        import kiro.oidc_provider as mod
        importlib.reload(mod)

    app = FastAPI()
    app.include_router(mod.router)
    return app, mod


# ---------------------------------------------------------------------------
# Happy path: full SSO flow
# ---------------------------------------------------------------------------

class TestFullSsoFlow:
    def test_full_flow_login_to_id_token(self):
        """
        Full round-trip:
          1. Simulate user already logged in (valid JWT → user loaded)
          2. GET /oauth/authorize?prompt=none&_gateway_token=... → 302 with code
          3. POST /oauth/token → 200 with id_token
          4. Verify id_token signature using /oauth/jwks
        """
        app, mod = _build_app()

        user = MagicMock()
        user.id = 42
        user.role = "admin"
        user.username = "alice"
        user.email = "alice@example.com"
        user.is_active = True

        mock_session = AsyncMock()

        async def _fake_session():
            yield mock_session

        client = TestClient(app, follow_redirects=False)

        # Step 1: authorize with prompt=none
        with (
            patch("kiro.oidc_provider.decode_token", return_value={"sub": "42", "type": "access"}),
            patch("kiro.oidc_provider._get_session", _fake_session),
            patch("kiro.oidc_provider.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            resp = client.get(
                "/oauth/authorize",
                params={
                    "client_id": "9router",
                    "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
                    "response_type": "code",
                    "state": "test-state",
                    "nonce": "test-nonce",
                    "prompt": "none",
                    "_gateway_token": "valid-token",
                },
            )

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "code=" in location
        assert "state=test-state" in location
        assert "error" not in location

        # Extract code from redirect
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(location)
        code = parse_qs(parsed.query)["code"][0]

        # Step 2: exchange code for id_token
        token_resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
                "client_id": "9router",
                "client_secret": "integration-secret",
            },
        )
        assert token_resp.status_code == 200
        body = token_resp.json()
        assert "id_token" in body
        assert body["token_type"] == "Bearer"

        # Step 3: verify id_token via JWKS
        jwks_resp = client.get("/oauth/jwks")
        assert jwks_resp.status_code == 200
        jwk = jwks_resp.json()["keys"][0]

        def _b64_to_int(s: str) -> int:
            padding = 4 - len(s) % 4
            s += "=" * (padding % 4)
            return int.from_bytes(base64.urlsafe_b64decode(s), "big")

        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        pub = RSAPublicNumbers(_b64_to_int(jwk["e"]), _b64_to_int(jwk["n"])).public_key()
        pub_pem = pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()

        payload = jwt.decode(body["id_token"], pub_pem, algorithms=["RS256"], audience="9router")
        assert payload["sub"] == "42"
        assert payload["email"] == "alice@example.com"
        assert payload["role"] == "admin"
        assert payload["nonce"] == "test-nonce"
        assert payload["iss"] == "http://localhost:18000"

    def test_discovery_endpoint_reachable(self):
        app, _ = _build_app()
        client = TestClient(app)
        resp = client.get("/.well-known/openid-configuration")
        assert resp.status_code == 200
        doc = resp.json()
        assert doc["issuer"] == "http://localhost:18000"
        assert doc["token_endpoint"].endswith("/oauth/token")
        assert doc["jwks_uri"].endswith("/oauth/jwks")


# ---------------------------------------------------------------------------
# Unauthenticated with prompt=none
# ---------------------------------------------------------------------------

class TestUnauthenticated:
    def test_prompt_none_no_token_returns_login_required(self):
        app, _ = _build_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get(
            "/oauth/authorize",
            params={
                "client_id": "9router",
                "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
                "response_type": "code",
                "prompt": "none",
            },
        )
        assert resp.status_code == 302
        assert "error=login_required" in resp.headers["location"]

    def test_prompt_none_expired_token_returns_login_required(self):
        app, _ = _build_app()
        client = TestClient(app, follow_redirects=False)

        with patch("kiro.oidc_provider.decode_token", return_value=None):
            resp = client.get(
                "/oauth/authorize",
                params={
                    "client_id": "9router",
                    "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
                    "response_type": "code",
                    "prompt": "none",
                    "_gateway_token": "expired-token",
                },
            )
        assert resp.status_code == 302
        assert "error=login_required" in resp.headers["location"]

    def test_no_prompt_none_redirects_to_login_page(self):
        app, _ = _build_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get(
            "/oauth/authorize",
            params={
                "client_id": "9router",
                "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
                "response_type": "code",
            },
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Token endpoint error cases
# ---------------------------------------------------------------------------

class TestTokenErrors:
    def _issue_code(self, mod) -> str:
        return mod._issue_code(
            user_id=1,
            role="admin",
            username="admin",
            email="admin@example.com",
            client_id="9router",
            redirect_uri="http://localhost:20128/api/auth/oidc/callback",
            nonce=None,
        )

    def test_expired_code_returns_400(self):
        app, mod = _build_app()
        code = self._issue_code(mod)
        mod._codes[code]["expires_at"] = time.time() - 1
        client = TestClient(app)
        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
                "client_id": "9router",
                "client_secret": "integration-secret",
            },
        )
        assert resp.status_code == 400

    def test_wrong_client_secret_returns_401(self):
        app, mod = _build_app()
        code = self._issue_code(mod)
        client = TestClient(app)
        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
                "client_id": "9router",
                "client_secret": "wrong-secret",
            },
        )
        assert resp.status_code == 401

    def test_code_reuse_returns_400(self):
        app, mod = _build_app()
        code = self._issue_code(mod)
        client = TestClient(app)
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
            "client_id": "9router",
            "client_secret": "integration-secret",
        }
        resp1 = client.post("/oauth/token", data=data)
        resp2 = client.post("/oauth/token", data=data)
        assert resp1.status_code == 200
        assert resp2.status_code == 400

    def test_nonexistent_code_returns_400(self):
        app, _ = _build_app()
        client = TestClient(app)
        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "does-not-exist",
                "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
                "client_id": "9router",
                "client_secret": "integration-secret",
            },
        )
        assert resp.status_code == 400
