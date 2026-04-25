import pytest
import time
from fastapi import HTTPException


class TestRateLimiter:
    """Tests for rate limiting in kiro/dashboard/routes_auth.py"""

    def setup_method(self):
        from kiro.dashboard import routes_auth
        routes_auth._login_attempts.clear()

    def test_allows_under_limit(self):
        from kiro.dashboard.routes_auth import _check_rate_limit
        for _ in range(4):
            _check_rate_limit("test-user")  # should not raise

    def test_blocks_at_limit(self):
        from kiro.dashboard.routes_auth import _check_rate_limit, MAX_LOGIN_ATTEMPTS
        for _ in range(MAX_LOGIN_ATTEMPTS):
            _check_rate_limit("test-user")
        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("test-user")
        assert exc_info.value.status_code == 429

    def test_different_keys_independent(self):
        from kiro.dashboard.routes_auth import _check_rate_limit, MAX_LOGIN_ATTEMPTS
        for _ in range(MAX_LOGIN_ATTEMPTS):
            _check_rate_limit("user-a")
        _check_rate_limit("user-b")  # should not raise

    def test_old_attempts_expire(self):
        from kiro.dashboard.routes_auth import _check_rate_limit, _login_attempts, MAX_LOGIN_ATTEMPTS, LOGIN_WINDOW_SECONDS
        old_time = time.time() - LOGIN_WINDOW_SECONDS - 1
        _login_attempts["test-user"] = [old_time] * MAX_LOGIN_ATTEMPTS
        _check_rate_limit("test-user")  # should not raise -- old attempts expired
