"""
Unit tests for kiro/model_override.py

Covers:
- resolve_model() / resolve_models() pure functions (no I/O)
- _normalize_targets()
"""

import pytest

from kiro.model_override import (
    OverrideConfig,
    resolve_model,
    resolve_models,
    _normalize_targets,
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

    def test_no_rules_default_auto_passthrough_without_has_default(self):
        # has_default=False (global override default): literal "auto" is NOT
        # enforced — unmatched models pass through unchanged.
        cfg = OverrideConfig(enabled=True, rules=[], default_model="auto")
        assert resolve_model("claude-haiku-4.5", cfg) == "claude-haiku-4.5"

    def test_no_rules_default_auto_enforced_with_has_default(self):
        # has_default=True (9router): literal "auto" IS enforced as a real model,
        # so unmatched models are rewritten to "auto". This is the bug fix.
        cfg = OverrideConfig(enabled=True, rules=[], default_model="auto", has_default=True)
        assert resolve_model("claude-haiku-4.5", cfg) == "auto"

    def test_has_default_enforces_auto_even_with_rules(self):
        # Rules still win, but when none match the "auto" default applies.
        cfg = OverrideConfig(enabled=True, rules=[{"from": "opus", "to": "GLM5"}],
                             default_model="auto", has_default=True)
        assert resolve_model("claude-opus-4.7", cfg) == "GLM5"
        assert resolve_model("claude-haiku-4.5", cfg) == "auto"

    def test_has_default_false_keeps_auto_passthrough_with_rules(self):
        # Without has_default, the "auto" default must still pass through.
        cfg = OverrideConfig(enabled=True, rules=[{"from": "opus", "to": "GLM5"}],
                             default_model="auto", has_default=False)
        assert resolve_model("claude-haiku-4.5", cfg) == "claude-haiku-4.5"


# =============================================================================
# resolve_models — multi-level failover candidates
# =============================================================================

class TestResolveModels:
    def test_disabled_config_is_single_passthrough(self):
        cfg = OverrideConfig(enabled=False, rules=[{"from": "opus", "to": ["a", "b"]}], default_model="deepseek")
        assert resolve_models("claude-opus-4.7", cfg) == ["claude-opus-4.7"]

    def test_string_to_yields_single_candidate(self):
        cfg = OverrideConfig(enabled=True, rules=[{"from": "opus", "to": "GLM5"}], default_model="auto")
        assert resolve_models("claude-opus-4.7", cfg) == ["GLM5"]

    def test_list_to_yields_ordered_candidates(self):
        cfg = OverrideConfig(enabled=True, rules=[{"from": "opus", "to": ["GLM5", "deepseek", "sonnet"]}], default_model="auto")
        assert resolve_models("claude-opus-4.7", cfg) == ["GLM5", "deepseek", "sonnet"]

    def test_list_to_filters_empty_and_whitespace(self):
        cfg = OverrideConfig(enabled=True, rules=[{"from": "opus", "to": ["GLM5", "", "  ", "deepseek"]}], default_model="auto")
        assert resolve_models("claude-opus-4.7", cfg) == ["GLM5", "deepseek"]

    def test_no_rule_default_yields_single_candidate(self):
        cfg = OverrideConfig(enabled=True, rules=[], default_model="deepseek")
        assert resolve_models("claude-opus-4.7", cfg) == ["deepseek"]

    def test_no_rule_auto_has_default_yields_auto(self):
        cfg = OverrideConfig(enabled=True, rules=[], default_model="auto", has_default=True)
        assert resolve_models("claude-haiku-4.5", cfg) == ["auto"]

    def test_no_rule_auto_no_has_default_passthrough(self):
        cfg = OverrideConfig(enabled=True, rules=[], default_model="auto", has_default=False)
        assert resolve_models("claude-haiku-4.5", cfg) == ["claude-haiku-4.5"]

    def test_first_matching_rule_wins_for_multi_level(self):
        cfg = OverrideConfig(enabled=True, rules=[
            {"from": "opus", "to": ["GLM5", "deepseek"]},
            {"from": "claude", "to": ["other"]},
        ], default_model="auto")
        assert resolve_models("claude-opus-4.7", cfg) == ["GLM5", "deepseek"]

    def test_resolve_model_is_first_candidate(self):
        cfg = OverrideConfig(enabled=True, rules=[{"from": "opus", "to": ["GLM5", "deepseek"]}], default_model="auto")
        assert resolve_model("claude-opus-4.7", cfg) == "GLM5"


# =============================================================================
# _normalize_targets — legacy string vs list normalization
# =============================================================================

class TestNormalizeTargets:
    def test_string_target(self):
        assert _normalize_targets({"to": "glm-5"}) == ["glm-5"]

    def test_list_target(self):
        assert _normalize_targets({"to": ["a", "b"]}) == ["a", "b"]

    def test_missing_to_returns_empty(self):
        assert _normalize_targets({"from": "opus"}) == []

    def test_empty_string_dropped(self):
        assert _normalize_targets({"to": ""}) == []

    def test_non_string_list_entries_dropped(self):
        assert _normalize_targets({"to": ["a", 3, None, "b"]}) == ["a", "b"]
