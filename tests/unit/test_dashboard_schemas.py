import pytest
import json
from pydantic import ValidationError
from kiro.dashboard.schemas import (
    UserCreate, UserUpdate, ApiKeyCreate, LoginRequest,
    SystemConfigUpdate, SystemConfigResponse, ModelOverrideRule,
)
from kiro.dashboard.routes_config import _to_response


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
        assert c.model_override_rules == []
        assert c.model_override_default == "auto"
        assert c.enable_usage_sharing is False


class TestModelOverrideRule:
    def test_from_alias_accepted(self):
        rule = ModelOverrideRule(**{"from": "opus", "to": "GLM5"})
        assert rule.from_ == "opus"
        assert rule.to == "GLM5"

    def test_serializes_with_from_alias(self):
        rule = ModelOverrideRule(**{"from": "opus", "to": "GLM5"})
        dumped = rule.model_dump(by_alias=True)
        assert "from" in dumped
        assert "from_" not in dumped
        assert dumped["from"] == "opus"

    def test_json_roundtrip(self):
        rule = ModelOverrideRule(**{"from": "sonnet", "to": "deepseek"})
        as_json = json.dumps(rule.model_dump(by_alias=True))
        parsed = json.loads(as_json)
        assert parsed == {"from": "sonnet", "to": "deepseek"}

    def test_system_config_update_with_rules(self):
        update = SystemConfigUpdate(
            enable_model_override=True,
            model_override_rules=[ModelOverrideRule(**{"from": "opus", "to": "GLM5"})],
            model_override_default="deepseek",
        )
        dumped = update.model_dump(exclude_unset=True, by_alias=True)
        assert dumped["model_override_rules"] == [{"from": "opus", "to": "GLM5"}]
        assert dumped["model_override_default"] == "deepseek"


class TestToResponse:
    def test_defaults_when_empty_raw(self):
        resp = _to_response({})
        assert resp.enable_model_override is False
        assert resp.model_override_rules == []
        assert resp.model_override_default == "auto"
        assert resp.enable_usage_sharing is False

    def test_parses_rules_from_json(self):
        raw = {
            "enable_model_override": "true",
            "model_override_rules": json.dumps([{"from": "opus", "to": "GLM5"}]),
            "model_override_default": "deepseek",
            "enable_usage_sharing": "false",
        }
        resp = _to_response(raw)
        assert resp.enable_model_override is True
        assert len(resp.model_override_rules) == 1
        assert resp.model_override_rules[0].from_ == "opus"
        assert resp.model_override_rules[0].to == "GLM5"
        assert resp.model_override_default == "deepseek"

    def test_invalid_rules_json_falls_back_to_empty(self):
        raw = {"model_override_rules": "not-json"}
        resp = _to_response(raw)
        assert resp.model_override_rules == []

    def test_non_list_rules_json_falls_back_to_empty(self):
        raw = {"model_override_rules": json.dumps({"from": "opus", "to": "GLM5"})}
        resp = _to_response(raw)
        assert resp.model_override_rules == []
