"""
Unit tests for kiro/model_override.py

Covers:
- resolve_model() pure function (no I/O)
- _fetch_override_config() with mocked DB and env fallbacks
- get_override_config() TTL cache behavior
- invalidate_cache()
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kiro.model_override import (
    OverrideConfig,
    resolve_model,
    get_override_config,
    invalidate_cache,
    _fetch_override_config,
)


# =============================================================================
# resolve_model — pure function, no mocking needed
# =============================================================================

class TestResolveModel:
    def test_disabled_config_is_noop(self):
        cfg = OverrideConfig(enabled=False, rules=[{"from": "opus", "to": "GLM5"}], default_model="deepseek")
        assert resolve_model("claude-opus-4.7", cfg) == "claude-opus-4.7"

    def test_no_rules_applies_default(self):
        cfg = OverrideConfig(enabled=True, rules=[], default_model="deepseek")
        assert resolve_model("claude-opus-4.7", cfg) == "deepseek"

    def test_no_rules_default_auto_is_passthrough(self):
        cfg = OverrideConfig(enabled=True, rules=[], default_model="auto")
        assert resolve_model("claude-haiku-4.5", cfg) == "claude-haiku-4.5"

    def test_first_rule_wins(self):
        cfg = OverrideConfig(enabled=True, rules=[
            {"from": "opus", "to": "GLM5"},
            {"from": "claude", "to": "other"},
        ], default_model="auto")
        assert resolve_model("claude-opus-4.7", cfg) == "GLM5"

    def test_second_rule_matches_when_first_does_not(self):
        cfg = OverrideConfig(enabled=True, rules=[
            {"from": "opus", "to": "GLM5"},
            {"from": "sonnet", "to": "deepseek"},
        ], default_model="auto")
        assert resolve_model("claude-sonnet-4.6", cfg) == "deepseek"

    def test_substring_match_on_normalized_name(self):
        cfg = OverrideConfig(enabled=True, rules=[{"from": "sonnet", "to": "deepseek"}], default_model="auto")
        # Date suffix should be stripped by normalize_model_name
        assert resolve_model("claude-sonnet-4-6-20250514", cfg) == "deepseek"

    def test_case_insensitive_match(self):
        cfg = OverrideConfig(enabled=True, rules=[{"from": "OPUS", "to": "GLM5"}], default_model="auto")
        assert resolve_model("claude-opus-4.7", cfg) == "GLM5"

    def test_no_match_uses_default(self):
        cfg = OverrideConfig(enabled=True, rules=[{"from": "opus", "to": "GLM5"}], default_model="deepseek")
        assert resolve_model("claude-haiku-4.5", cfg) == "deepseek"

    def test_no_match_default_auto_passthrough(self):
        cfg = OverrideConfig(enabled=True, rules=[{"from": "opus", "to": "GLM5"}], default_model="auto")
        assert resolve_model("claude-haiku-4.5", cfg) == "claude-haiku-4.5"

    def test_empty_from_pattern_skipped(self):
        cfg = OverrideConfig(enabled=True, rules=[
            {"from": "", "to": "GLM5"},
            {"from": "haiku", "to": "deepseek"},
        ], default_model="auto")
        assert resolve_model("claude-haiku-4.5", cfg) == "deepseek"

    def test_rule_to_same_model_is_noop(self):
        cfg = OverrideConfig(enabled=True, rules=[{"from": "opus", "to": "claude-opus-4.7"}], default_model="auto")
        assert resolve_model("claude-opus-4.7", cfg) == "claude-opus-4.7"

    def test_missing_to_key_falls_back_to_original(self):
        cfg = OverrideConfig(enabled=True, rules=[{"from": "opus"}], default_model="auto")
        assert resolve_model("claude-opus-4.7", cfg) == "claude-opus-4.7"


# =============================================================================
# _fetch_override_config — DB and env fallback paths
# =============================================================================

class TestFetchOverrideConfig:
    @pytest.mark.asyncio
    async def test_no_db_api_key_mode_returns_disabled(self):
        with patch("kiro.config.API_KEY_MODE", True), \
             patch("kiro.db.engine.async_session_factory", None):
            cfg = await _fetch_override_config()
        assert cfg.enabled is False
        assert cfg.rules == []

    @pytest.mark.asyncio
    async def test_no_db_non_api_key_mode_uses_env(self):
        with patch("kiro.config.API_KEY_MODE", False), \
             patch("kiro.db.engine.async_session_factory", None), \
             patch("kiro.config.ENABLE_MODEL_OVERRIDE", True), \
             patch("kiro.config.ENFORCED_GLOBAL_MODEL", "deepseek"):
            cfg = await _fetch_override_config()
        assert cfg.enabled is True
        assert cfg.default_model == "deepseek"
        assert cfg.rules == []

    @pytest.mark.asyncio
    async def test_db_reads_rules_and_default(self):
        rules = [{"from": "opus", "to": "GLM5"}]
        mock_cfg = {
            "enable_model_override": "true",
            "model_override_rules": json.dumps(rules),
            "model_override_default": "deepseek",
        }
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("kiro.db.engine.async_session_factory", mock_factory), \
             patch("kiro.db.repositories.get_all_config", AsyncMock(return_value=mock_cfg)):
            cfg = await _fetch_override_config()

        assert cfg.enabled is True
        assert cfg.rules == rules
        assert cfg.default_model == "deepseek"

    @pytest.mark.asyncio
    async def test_db_soft_migration_reads_old_key(self):
        mock_cfg = {
            "enable_model_override": "true",
            "model_override_rules": "[]",
            # model_override_default absent, enforced_global_model present
            "enforced_global_model": "legacy-model",
        }
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("kiro.db.engine.async_session_factory", mock_factory), \
             patch("kiro.db.repositories.get_all_config", AsyncMock(return_value=mock_cfg)):
            cfg = await _fetch_override_config()

        assert cfg.default_model == "legacy-model"

    @pytest.mark.asyncio
    async def test_db_invalid_rules_json_falls_back_to_empty(self):
        mock_cfg = {
            "enable_model_override": "true",
            "model_override_rules": "not-valid-json",
            "model_override_default": "auto",
        }
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("kiro.db.engine.async_session_factory", mock_factory), \
             patch("kiro.db.repositories.get_all_config", AsyncMock(return_value=mock_cfg)):
            cfg = await _fetch_override_config()

        assert cfg.rules == []
        assert cfg.enabled is True

    @pytest.mark.asyncio
    async def test_db_exception_falls_back_to_env(self):
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("kiro.db.engine.async_session_factory", mock_factory), \
             patch("kiro.config.API_KEY_MODE", False), \
             patch("kiro.config.ENABLE_MODEL_OVERRIDE", True), \
             patch("kiro.config.ENFORCED_GLOBAL_MODEL", "fallback-model"):
            cfg = await _fetch_override_config()

        assert cfg.enabled is True
        assert cfg.default_model == "fallback-model"


# =============================================================================
# get_override_config — TTL cache
# =============================================================================

class TestGetOverrideConfig:
    @pytest.mark.asyncio
    async def test_cache_is_populated_on_first_call(self):
        invalidate_cache()
        expected = OverrideConfig(enabled=True, rules=[], default_model="deepseek")
        with patch("kiro.model_override._fetch_override_config", AsyncMock(return_value=expected)):
            cfg = await get_override_config()
        assert cfg == expected

    @pytest.mark.asyncio
    async def test_cache_is_reused_within_ttl(self):
        invalidate_cache()
        expected = OverrideConfig(enabled=True, rules=[], default_model="deepseek")
        fetch_mock = AsyncMock(return_value=expected)
        with patch("kiro.model_override._fetch_override_config", fetch_mock):
            await get_override_config()
            await get_override_config()
        assert fetch_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_invalidate_cache_forces_refetch(self):
        invalidate_cache()
        cfg1 = OverrideConfig(enabled=True, rules=[], default_model="model-a")
        cfg2 = OverrideConfig(enabled=True, rules=[], default_model="model-b")
        fetch_mock = AsyncMock(side_effect=[cfg1, cfg2])
        with patch("kiro.model_override._fetch_override_config", fetch_mock):
            r1 = await get_override_config()
            invalidate_cache()
            r2 = await get_override_config()
        assert r1.default_model == "model-a"
        assert r2.default_model == "model-b"
        assert fetch_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self):
        invalidate_cache()
        cfg1 = OverrideConfig(enabled=True, rules=[], default_model="old")
        cfg2 = OverrideConfig(enabled=True, rules=[], default_model="new")
        fetch_mock = AsyncMock(side_effect=[cfg1, cfg2])
        with patch("kiro.model_override._fetch_override_config", fetch_mock), \
             patch("kiro.model_override._CACHE_TTL", 0):
            await get_override_config()
            await asyncio.sleep(0.01)
            r2 = await get_override_config()
        assert r2.default_model == "new"
        assert fetch_mock.call_count == 2
