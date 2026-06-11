# -*- coding: utf-8 -*-
"""
Unit tests for kiro/oidc_provider.py.

Tests cover:
- OIDC discovery document
- JWKS endpoint
- Authorization endpoint (with/without session, prompt=none, invalid client)
- Token endpoint (happy path, expired code, wrong secret, wrong client, reuse)
- Authorization code store eviction
- id_token structure and RS256 signature
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(clients: dict | None = None, client_secret: str = "test-secret"):
    """Build a minimal FastAPI app with oidc_provider router, optionally patching clients."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "OIDC_CLIENT_SECRET": client_secret,
            "OIDC_REDIRECT_URI": "http://localhost:20128/api/auth/oidc/callback",
            "OIDC_ISSUER_URL": "http://localhost:18000",
        },
        clear=False,
    ):
        import kiro.oidc_provider as mod
        importlib.reload(mod)

        if clients is not None:
            mod._CLIENTS = clients

        app = FastAPI()
        app.include_router(mod.router)
        return app, mod


def _active_user(user_id: int = 1, role: str = "admin", username: str = "admin", email: str = "admin@example.com"):
    user = MagicMock()
    user.id = user_id
    user.role = role
    user.username = username
    user.email = email
    user.is_active = True
    return user


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestOidcDiscovery:
    def test_discovery_returns_required_fields(self):
        app, _ = _make_app()
        client = TestClient(app)
        resp = client.get("/.well-known/openid-configuration")
        assert resp.status_code == 200
        body = resp.json()
        assert body["issuer"] == "http://localhost:18000"
        assert "/oauth/authorize" in body["authorization_endpoint"]
        assert "/oauth/token" in body["token_endpoint"]
        assert "/oauth/jwks" in body["jwks_uri"]
        assert "code" in body["response_types_supported"]
        assert "RS256" in body["id_token_signing_alg_values_supported"]

    def test_discovery_includes_pkce(self):
        app, _ = _make_app()
        client = TestClient(app)
        body = client.get("/.well-known/openid-configuration").json()
        assert "S256" in body["code_challenge_methods_supported"]


# ---------------------------------------------------------------------------
# JWKS
# ---------------------------------------------------------------------------

class TestJwks:
    def test_jwks_returns_rsa_key(self):
        app, _ = _make_app()
        client = TestClient(app)
        resp = client.get("/oauth/jwks")
        assert resp.status_code == 200
        keys = resp.json()["keys"]
        assert len(keys) == 1
        key = keys[0]
        assert key["kty"] == "RSA"
        assert key["alg"] == "RS256"
        assert key["use"] == "sig"
        assert "n" in key and "e" in key and "kid" in key

    def test_jwks_kid_is_stable(self):
        app, mod = _make_app()
        client = TestClient(app)
        k1 = client.get("/oauth/jwks").json()["keys"][0]["kid"]
        k2 = client.get("/oauth/jwks").json()["keys"][0]["kid"]
        assert k1 == k2


# ---------------------------------------------------------------------------
# Authorization endpoint
# ---------------------------------------------------------------------------

class TestAuthorize:
    def _base_params(self, **overrides):
        p = {
            "client_id": "9router",
            "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
            "response_type": "code",
            "state": "xyz",
        }
        p.update(overrides)
        return p

    def _call(self, token: str | None = None, **params):
        app, mod = _make_app()
        client = TestClient(app, follow_redirects=False)
        if token:
            params["_gateway_token"] = token
        return client.get("/oauth/authorize", params=self._base_params(**params)), mod

    def _make_valid_token(self, mod, user_id=1, role="admin"):
        """Create a real HS256 access token using the mod's decode_token logic."""
        from kiro.dashboard.jwt_auth import create_access_token
        return create_access_token(user_id=user_id, role=role, username="admin")

    def test_unknown_client_id_returns_400(self):
        resp, _ = self._call(client_id="unknown")
        assert resp.status_code == 400

    def test_unregistered_redirect_uri_returns_400(self):
        resp, _ = self._call(redirect_uri="http://evil.example.com/callback")
        assert resp.status_code == 400

    def test_wrong_response_type_returns_400(self):
        app, mod = _make_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get(
            "/oauth/authorize",
            params={**self._base_params(), "response_type": "token"},
        )
        assert resp.status_code == 400

    def test_prompt_none_without_session_returns_login_required(self):
        app, mod = _make_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get(
            "/oauth/authorize",
            params=self._base_params(prompt="none"),
        )
        assert resp.status_code == 302
        assert "error=login_required" in resp.headers["location"]

    def test_prompt_none_with_invalid_token_returns_login_required(self):
        app, mod = _make_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get(
            "/oauth/authorize",
            params=self._base_params(prompt="none", _gateway_token="bad.token.here"),
        )
        assert resp.status_code == 302
        assert "error=login_required" in resp.headers["location"]

    def test_no_session_without_prompt_none_redirects_to_login(self):
        app, mod = _make_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/oauth/authorize", params=self._base_params())
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]

    def test_valid_token_issues_code_and_redirects(self):
        app, mod = _make_app()
        http_client = TestClient(app, follow_redirects=False)

        user = _active_user()
        mock_session = AsyncMock()

        async def _fake_get_session():
            yield mock_session

        with (
            patch("kiro.dashboard.jwt_auth.JWT_SECRET", "test-secret"),
            patch("kiro.config.JWT_SECRET", "test-secret"),
            patch("kiro.config.JWT_ACCESS_EXPIRY", 900),
        ):
            import importlib
            import kiro.dashboard.jwt_auth as jwt_mod
            importlib.reload(jwt_mod)
            token = jwt_mod.create_access_token(user_id=1, role="admin", username="admin")

        with (
            patch("kiro.oidc_provider.decode_token", return_value={"sub": "1", "type": "access"}),
            patch("kiro.oidc_provider._get_session", _fake_get_session),
            patch("kiro.oidc_provider.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            resp = http_client.get(
                "/oauth/authorize",
                params=self._base_params(prompt="none", _gateway_token=token),
            )

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "code=" in location
        assert "state=xyz" in location
        assert "error" not in location

    def test_state_preserved_in_redirect(self):
        app, mod = _make_app()
        http_client = TestClient(app, follow_redirects=False)
        user = _active_user()
        mock_session = AsyncMock()

        async def _fake_get_session():
            yield mock_session

        with (
            patch("kiro.oidc_provider.decode_token", return_value={"sub": "1", "type": "access"}),
            patch("kiro.oidc_provider._get_session", _fake_get_session),
            patch("kiro.oidc_provider.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            resp = http_client.get(
                "/oauth/authorize",
                params=self._base_params(prompt="none", _gateway_token="tok", state="my-state-123"),
            )

        assert "state=my-state-123" in resp.headers["location"]

    def test_inactive_user_with_prompt_none_returns_login_required(self):
        app, mod = _make_app()
        http_client = TestClient(app, follow_redirects=False)
        user = _active_user()
        user.is_active = False
        mock_session = AsyncMock()

        async def _fake_get_session():
            yield mock_session

        with (
            patch("kiro.oidc_provider.decode_token", return_value={"sub": "1", "type": "access"}),
            patch("kiro.oidc_provider._get_session", _fake_get_session),
            patch("kiro.oidc_provider.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            resp = http_client.get(
                "/oauth/authorize",
                params=self._base_params(prompt="none", _gateway_token="tok"),
            )

        assert "error=login_required" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Token endpoint
# ---------------------------------------------------------------------------

class TestToken:
    def _token_params(self, code: str, **overrides):
        p = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
            "client_id": "9router",
            "client_secret": "test-secret",
        }
        p.update(overrides)
        return p

    def _issue_code(self, mod) -> str:
        return mod._issue_code(
            user_id=1,
            role="admin",
            username="admin",
            email="admin@example.com",
            client_id="9router",
            redirect_uri="http://localhost:20128/api/auth/oidc/callback",
            nonce="test-nonce",
        )

    def test_happy_path_returns_id_token(self):
        app, mod = _make_app()
        code = self._issue_code(mod)
        client = TestClient(app)
        resp = client.post("/oauth/token", data=self._token_params(code))
        assert resp.status_code == 200
        body = resp.json()
        assert "id_token" in body
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == mod._ID_TOKEN_TTL

    def test_id_token_is_valid_rs256_jwt(self):
        app, mod = _make_app()
        code = self._issue_code(mod)
        client = TestClient(app)
        resp = client.post("/oauth/token", data=self._token_params(code))
        id_token = resp.json()["id_token"]

        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        pub_pem = mod._PUBLIC_KEY.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
        payload = jwt.decode(id_token, pub_pem, algorithms=["RS256"], audience="9router")
        assert payload["sub"] == "1"
        assert payload["role"] == "admin"
        assert payload["email"] == "admin@example.com"
        assert payload["nonce"] == "test-nonce"
        assert payload["iss"] == "http://localhost:18000"

    def test_code_is_single_use(self):
        app, mod = _make_app()
        code = self._issue_code(mod)
        client = TestClient(app)
        resp1 = client.post("/oauth/token", data=self._token_params(code))
        resp2 = client.post("/oauth/token", data=self._token_params(code))
        assert resp1.status_code == 200
        assert resp2.status_code == 400

    def test_expired_code_returns_400(self):
        app, mod = _make_app()
        code = self._issue_code(mod)
        # Backdate the expiry
        mod._codes[code]["expires_at"] = time.time() - 1
        client = TestClient(app)
        resp = client.post("/oauth/token", data=self._token_params(code))
        assert resp.status_code == 400

    def test_wrong_client_secret_returns_401(self):
        app, mod = _make_app()
        code = self._issue_code(mod)
        client = TestClient(app)
        resp = client.post("/oauth/token", data=self._token_params(code, client_secret="wrong"))
        assert resp.status_code == 401

    def test_unknown_client_id_returns_401(self):
        app, mod = _make_app()
        code = self._issue_code(mod)
        client = TestClient(app)
        resp = client.post("/oauth/token", data=self._token_params(code, client_id="evil", client_secret="x"))
        assert resp.status_code == 401

    def test_redirect_uri_mismatch_returns_400(self):
        app, mod = _make_app()
        code = self._issue_code(mod)
        client = TestClient(app)
        resp = client.post(
            "/oauth/token",
            data=self._token_params(code, redirect_uri="http://evil.example.com/callback"),
        )
        assert resp.status_code == 400

    def test_invalid_code_returns_400(self):
        app, mod = _make_app()
        client = TestClient(app)
        resp = client.post("/oauth/token", data=self._token_params("nonexistent-code"))
        assert resp.status_code == 400

    def test_wrong_grant_type_returns_400(self):
        app, mod = _make_app()
        code = self._issue_code(mod)
        client = TestClient(app)
        resp = client.post("/oauth/token", data=self._token_params(code, grant_type="implicit"))
        assert resp.status_code == 400

    def test_client_id_mismatch_returns_400(self):
        """Code issued to 9router cannot be exchanged by another client."""
        app, mod = _make_app(
            clients={
                "9router": {"client_id": "9router", "client_secret": "test-secret", "redirect_uris": ["http://localhost:20128/api/auth/oidc/callback"]},
                "other": {"client_id": "other", "client_secret": "other-secret", "redirect_uris": ["http://localhost:20128/api/auth/oidc/callback"]},
            }
        )
        code = self._issue_code(mod)
        client = TestClient(app)
        resp = client.post("/oauth/token", data=self._token_params(code, client_id="other", client_secret="other-secret"))
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Code store eviction
# ---------------------------------------------------------------------------

class TestCodeStore:
    def test_expired_codes_are_evicted(self):
        _, mod = _make_app()
        # Insert an already-expired code
        mod._codes["expired-code"] = {
            "user_id": 1, "role": "admin", "username": "x", "email": "x@x.com",
            "client_id": "9router", "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
            "nonce": None, "expires_at": time.time() - 10,
        }
        before = len(mod._codes)
        mod._evict_expired()
        assert len(mod._codes) < before
        assert "expired-code" not in mod._codes

    def test_max_codes_evicts_oldest_on_overflow(self):
        _, mod = _make_app()
        mod._codes.clear()
        # Fill to max
        for i in range(mod._CODE_MAX):
            mod._codes[f"code-{i}"] = {
                "user_id": i, "role": "user", "username": "u", "email": "u@u.com",
                "client_id": "9router", "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
                "nonce": None, "expires_at": time.time() + 60 + i,
            }
        # Issue one more — should evict the entry with the smallest expires_at
        new_code = mod._issue_code(
            user_id=999, role="admin", username="admin", email="a@a.com",
            client_id="9router", redirect_uri="http://localhost:20128/api/auth/oidc/callback",
            nonce=None,
        )
        assert len(mod._codes) == mod._CODE_MAX
        assert new_code in mod._codes
        # The oldest (code-0, smallest expires_at) should have been evicted
        assert "code-0" not in mod._codes

    def test_consume_code_removes_it(self):
        _, mod = _make_app()
        code = mod._issue_code(
            user_id=1, role="admin", username="u", email="u@u.com",
            client_id="9router", redirect_uri="http://x", nonce=None,
        )
        entry = mod._consume_code(code)
        assert entry is not None
        assert code not in mod._codes

    def test_consume_missing_code_returns_none(self):
        _, mod = _make_app()
        assert mod._consume_code("does-not-exist") is None

    def test_consume_expired_code_returns_none(self):
        _, mod = _make_app()
        code = mod._issue_code(
            user_id=1, role="admin", username="u", email="u@u.com",
            client_id="9router", redirect_uri="http://x", nonce=None,
        )
        mod._codes[code]["expires_at"] = time.time() - 1
        assert mod._consume_code(code) is None


# ---------------------------------------------------------------------------
# JWKS / id_token cross-verification
# ---------------------------------------------------------------------------

class TestJwksCrossVerification:
    def test_id_token_verifiable_via_jwks_public_key(self):
        """Full round-trip: issue code → exchange → verify id_token using JWKS n/e."""
        import base64
        import struct

        app, mod = _make_app()
        code = mod._issue_code(
            user_id=7, role="user", username="bob", email="bob@example.com",
            client_id="9router", redirect_uri="http://localhost:20128/api/auth/oidc/callback",
            nonce=None,
        )
        client = TestClient(app)
        token_resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost:20128/api/auth/oidc/callback",
                "client_id": "9router",
                "client_secret": "test-secret",
            },
        )
        assert token_resp.status_code == 200
        id_token = token_resp.json()["id_token"]

        # Fetch JWKS and reconstruct public key
        jwks_resp = client.get("/oauth/jwks")
        jwk = jwks_resp.json()["keys"][0]

        def _decode_b64(s: str) -> int:
            padding = 4 - len(s) % 4
            s += "=" * (padding % 4)
            return int.from_bytes(base64.urlsafe_b64decode(s), "big")

        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        n = _decode_b64(jwk["n"])
        e = _decode_b64(jwk["e"])
        pub = RSAPublicNumbers(e, n).public_key()
        pub_pem = pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()

        payload = jwt.decode(id_token, pub_pem, algorithms=["RS256"], audience="9router")
        assert payload["sub"] == "7"
        assert payload["email"] == "bob@example.com"
