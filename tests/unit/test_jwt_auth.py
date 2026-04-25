import pytest
from unittest.mock import patch


class TestJwtAuth:
    """Tests for kiro/dashboard/jwt_auth.py"""

    def test_create_access_token_contains_correct_claims(self):
        with patch("kiro.config.JWT_SECRET", "test-secret"), \
             patch("kiro.config.JWT_ACCESS_EXPIRY", 900):
            # Force re-read of patched config values by reimporting
            import importlib
            import kiro.dashboard.jwt_auth as mod
            importlib.reload(mod)
            token = mod.create_access_token(user_id=42, role="admin")
            payload = mod.decode_token(token)
            assert payload is not None
            assert payload["sub"] == "42"
            assert payload["role"] == "admin"
            assert payload["type"] == "access"

    def test_create_refresh_token_contains_correct_claims(self):
        with patch("kiro.config.JWT_SECRET", "test-secret"), \
             patch("kiro.config.JWT_REFRESH_EXPIRY", 604800):
            import importlib
            import kiro.dashboard.jwt_auth as mod
            importlib.reload(mod)
            token = mod.create_refresh_token(user_id=42)
            payload = mod.decode_token(token)
            assert payload is not None
            assert payload["sub"] == "42"
            assert payload["type"] == "refresh"
            assert "role" not in payload

    def test_decode_invalid_token_returns_none(self):
        with patch("kiro.config.JWT_SECRET", "test-secret"):
            import importlib
            import kiro.dashboard.jwt_auth as mod
            importlib.reload(mod)
            assert mod.decode_token("invalid.token.here") is None

    def test_decode_wrong_secret_returns_none(self):
        with patch("kiro.config.JWT_SECRET", "secret-1"), \
             patch("kiro.config.JWT_ACCESS_EXPIRY", 900):
            import importlib
            import kiro.dashboard.jwt_auth as mod
            importlib.reload(mod)
            token = mod.create_access_token(user_id=1, role="user")

        with patch("kiro.config.JWT_SECRET", "secret-2"):
            importlib.reload(mod)
            assert mod.decode_token(token) is None

    def test_expired_token_returns_none(self):
        with patch("kiro.config.JWT_SECRET", "test-secret"), \
             patch("kiro.config.JWT_ACCESS_EXPIRY", -1):
            import importlib
            import kiro.dashboard.jwt_auth as mod
            importlib.reload(mod)
            token = mod.create_access_token(user_id=1, role="user")
            assert mod.decode_token(token) is None
