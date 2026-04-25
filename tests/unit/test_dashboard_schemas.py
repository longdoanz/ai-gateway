import pytest
from pydantic import ValidationError
from kiro.dashboard.schemas import (
    UserCreate, UserUpdate, ApiKeyCreate, LoginRequest,
    SystemConfigUpdate, SystemConfigResponse,
)


class TestDashboardSchemas:
    """Tests for kiro/dashboard/schemas.py validation rules"""

    def test_user_create_valid(self):
        u = UserCreate(username="testuser", password="secret123")
        assert u.role == "user"

    def test_user_create_admin_role(self):
        u = UserCreate(username="admin", password="secret123", role="admin")
        assert u.role == "admin"

    def test_user_create_invalid_role(self):
        with pytest.raises(ValidationError):
            UserCreate(username="test", password="secret123", role="superadmin")

    def test_user_create_short_username(self):
        with pytest.raises(ValidationError):
            UserCreate(username="ab", password="secret123")

    def test_user_create_short_password(self):
        with pytest.raises(ValidationError):
            UserCreate(username="testuser", password="12345")

    def test_user_update_partial(self):
        u = UserUpdate(is_active=False)
        dumped = u.model_dump(exclude_unset=True)
        assert dumped == {"is_active": False}

    def test_user_update_empty(self):
        u = UserUpdate()
        dumped = u.model_dump(exclude_unset=True)
        assert dumped == {}

    def test_api_key_create_min_length(self):
        with pytest.raises(ValidationError):
            ApiKeyCreate(raw_key="short")

    def test_api_key_create_valid(self):
        k = ApiKeyCreate(raw_key="sk-proj-abcdefghijklmnop")
        assert k.raw_key == "sk-proj-abcdefghijklmnop"

    def test_login_request(self):
        lr = LoginRequest(username="admin", password="pass")
        assert lr.username == "admin"

    def test_system_config_update_partial(self):
        c = SystemConfigUpdate(enable_model_override=True)
        dumped = c.model_dump(exclude_unset=True)
        assert dumped == {"enable_model_override": True}

    def test_system_config_response_defaults(self):
        c = SystemConfigResponse()
        assert c.enable_model_override is False
        assert c.enforced_global_model == "auto"
        assert c.enable_usage_sharing is False
