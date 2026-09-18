# -*- coding: utf-8 -*-

"""
Unit tests for Service Account request-path enforcement.

Covers:
- kiro/service_accounts.py: resolve_service_account, is_model_allowed
  (normalization rules), make_service_account_usage_cb.
- kiro/routes_openai.py chat_completions / GET /v1/models: allowlist
  enforcement runs before the unconditional 9router forward, forwards with
  apply_override=False, and /v1/models returns the account's allowlist.
- kiro/routes_anthropic.py messages: same enforcement, Anthropic-shaped
  error body.

The data layer itself (repositories.py CRUD, key issuance, usage increments)
is already covered by tests/unit/test_service_accounts.py — this file only
covers the resolver/matching helpers and the request-path wiring.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kiro.service_accounts import (
    ServiceAccountContext,
    is_model_allowed,
    make_service_account_usage_cb,
    resolve_service_account,
)


# ---------------------------------------------------------------------------
# is_model_allowed — normalization rules
# ---------------------------------------------------------------------------

class TestIsModelAllowed:
    def test_exact_match(self):
        assert is_model_allowed("kiro/claude-sonnet-4", ["kiro/claude-sonnet-4"]) is True

    def test_empty_allowlist_is_fail_closed(self):
        assert is_model_allowed("kiro/claude-sonnet-4", []) is False

    def test_no_match_returns_false(self):
        assert is_model_allowed("openai/gpt-5", ["kiro/claude-sonnet-4"]) is False

    def test_case_insensitive(self):
        assert is_model_allowed("KIRO/Claude-Sonnet-4", ["kiro/claude-sonnet-4"]) is True

    def test_bare_model_matches_prefixed_allowlist_entry(self):
        # Client sends the bare model name; allowlist has the 9router
        # catalog form "{alias}/{model}".
        assert is_model_allowed("claude-sonnet-4", ["kiro/claude-sonnet-4"]) is True

    def test_context_window_suffix_stripped_on_requested_model(self):
        # "claude-opus-5[1m]" (Claude Code's context-window suffix) against
        # an allowlist entry "kiro/claude-opus-5".
        assert is_model_allowed("claude-opus-5[1m]", ["kiro/claude-opus-5"]) is True

    def test_context_window_suffix_stripped_on_allowlist_entry(self):
        # Reverse: the allowlist itself carries the suffix, the client sends
        # a plain prefixed model id.
        assert is_model_allowed("kiro/claude-opus-5", ["kiro/claude-opus-5[1m]"]) is True

    def test_fully_prefixed_request_matches_bare_allowlist_entry(self):
        # Client sends the fully-prefixed form even though the allowlist
        # entry itself has no prefix.
        assert is_model_allowed("kiro/claude-opus-5[1m]", ["claude-opus-5"]) is True

    def test_none_model_returns_false(self):
        assert is_model_allowed(None, ["kiro/claude-sonnet-4"]) is False

    def test_empty_string_model_returns_false(self):
        assert is_model_allowed("", ["kiro/claude-sonnet-4"]) is False

    def test_does_not_cross_match_different_models_with_slash(self):
        assert is_model_allowed("gpt-5", ["kiro/claude-sonnet-4"]) is False


# ---------------------------------------------------------------------------
# resolve_service_account
# ---------------------------------------------------------------------------

class TestResolveServiceAccount:
    @pytest.mark.asyncio
    async def test_none_token_returns_none(self):
        assert await resolve_service_account(None) is None

    @pytest.mark.asyncio
    async def test_non_izisa_token_returns_none_without_db_lookup(self):
        with patch("kiro.service_accounts._is_db_configured") as mock_configured:
            result = await resolve_service_account("iziaigw_sometoken")
            assert result is None
            mock_configured.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_db_not_configured(self):
        with patch("kiro.service_accounts._is_db_configured", return_value=False):
            result = await resolve_service_account("izisa_sometoken")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_key_not_found(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("kiro.service_accounts._is_db_configured", return_value=True),
            patch("kiro.db.engine.async_session_factory", mock_factory),
            patch("kiro.db.repositories.get_service_account_key_by_hash", AsyncMock(return_value=None)),
        ):
            result = await resolve_service_account("izisa_sometoken")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_context_on_success(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        sa_key = MagicMock(service_account_id=7)
        service_account = MagicMock(id=7, is_active=True, allowed_models='["kiro/claude-sonnet-4"]')
        service_account.name = "ci-bot"  # "name" is a reserved Mock() constructor kwarg

        with (
            patch("kiro.service_accounts._is_db_configured", return_value=True),
            patch("kiro.db.engine.async_session_factory", mock_factory),
            patch("kiro.db.repositories.get_service_account_key_by_hash", AsyncMock(return_value=sa_key)),
            patch("kiro.db.repositories.get_service_account_by_id", AsyncMock(return_value=service_account)),
        ):
            result = await resolve_service_account("izisa_sometoken")

        assert isinstance(result, ServiceAccountContext)
        assert result.id == 7
        assert result.name == "ci-bot"
        assert result.allowed_models == ["kiro/claude-sonnet-4"]

    @pytest.mark.asyncio
    async def test_never_raises_on_unexpected_error(self):
        with (
            patch("kiro.service_accounts._is_db_configured", return_value=True),
            patch("kiro.db.engine.async_session_factory", side_effect=Exception("boom")),
        ):
            result = await resolve_service_account("izisa_sometoken")
            assert result is None


# ---------------------------------------------------------------------------
# make_service_account_usage_cb
# ---------------------------------------------------------------------------

class TestMakeServiceAccountUsageCb:
    def test_returns_none_when_db_not_configured(self):
        with patch("kiro.service_accounts._is_db_configured", return_value=False):
            assert make_service_account_usage_cb(1) is None

    @pytest.mark.asyncio
    async def test_records_monthly_and_daily_usage(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_increment_usage = AsyncMock()
        mock_increment_daily = AsyncMock()

        with (
            patch("kiro.service_accounts._is_db_configured", return_value=True),
            patch("kiro.db.engine.async_session_factory", mock_factory),
            patch("kiro.db.repositories.increment_service_account_usage", mock_increment_usage),
            patch("kiro.db.repositories.increment_service_account_daily_usage", mock_increment_daily),
        ):
            cb = make_service_account_usage_cb(7)
            assert cb is not None
            await cb(100, 42, "kiro/claude-sonnet-4")

        mock_increment_usage.assert_called_once()
        assert mock_increment_usage.call_args[0][1] == 7  # service_account_id
        mock_increment_daily.assert_called_once()
        daily_args = mock_increment_daily.call_args[0]
        assert daily_args[1] == 7  # service_account_id
        assert daily_args[3] == 100  # input_tokens
        assert daily_args[4] == 42  # output_tokens
        assert mock_increment_daily.call_args.kwargs["model"] == "kiro/claude-sonnet-4"

    @pytest.mark.asyncio
    async def test_swallows_tracking_errors(self):
        mock_factory = MagicMock(side_effect=Exception("db down"))

        with (
            patch("kiro.service_accounts._is_db_configured", return_value=True),
            patch("kiro.db.engine.async_session_factory", mock_factory),
        ):
            cb = make_service_account_usage_cb(7)
            # Must not raise even though the DB call fails internally.
            await cb(1, 1, "kiro/claude-sonnet-4")


# ---------------------------------------------------------------------------
# Route-level enforcement — OpenAI /v1/chat/completions
# ---------------------------------------------------------------------------

def _sa_context(allowed=None):
    return ServiceAccountContext(id=1, name="ci-bot", allowed_models=allowed or [])


class TestOpenAIChatCompletionsServiceAccountEnforcement:
    def test_allowed_model_forwards_to_nine_router_with_override_disabled(self, test_client):
        sa = _sa_context(["kiro/claude-sonnet-4"])
        mock_forward = AsyncMock(return_value=MagicMock(status_code=200))

        with (
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=sa)),
            patch("kiro.routes_openai.forward_to_nine_router", mock_forward),
        ):
            test_client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer izisa_testtoken"},
                json={
                    "model": "claude-sonnet-4",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        mock_forward.assert_called_once()
        assert mock_forward.call_args.kwargs["apply_override"] is False
        assert mock_forward.call_args.kwargs["on_usage"] is not None

    def test_disallowed_model_returns_403_and_does_not_forward(self, test_client):
        sa = _sa_context(["kiro/claude-sonnet-4"])
        mock_forward = AsyncMock()

        with (
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=sa)),
            patch("kiro.routes_openai.forward_to_nine_router", mock_forward),
        ):
            response = test_client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer izisa_testtoken"},
                json={
                    "model": "openai/gpt-5",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        assert response.status_code == 403
        assert "not permitted" in response.json()["error"]["message"]
        mock_forward.assert_not_called()

    def test_empty_allowlist_returns_403(self, test_client):
        sa = _sa_context([])
        mock_forward = AsyncMock()

        with (
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=sa)),
            patch("kiro.routes_openai.forward_to_nine_router", mock_forward),
        ):
            response = test_client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer izisa_testtoken"},
                json={
                    "model": "kiro/claude-sonnet-4",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        assert response.status_code == 403
        mock_forward.assert_not_called()

    def test_non_service_account_token_is_unaffected(self, test_client, valid_proxy_api_key):
        """A normal PROXY_API_KEY request must not be treated as a service
        account — it still forwards to 9router, but via the unconditional
        gateway-key path (apply_override defaults to True), not the
        service-account short-circuit (apply_override=False)."""
        mock_forward = AsyncMock(return_value=MagicMock(status_code=200))

        with (
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=None)),
            patch("kiro.routes_openai.forward_to_nine_router", mock_forward),
        ):
            response = test_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
                json={
                    "model": "claude-sonnet-4-5",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        assert response.status_code == 200
        mock_forward.assert_called_once()
        assert "apply_override" not in mock_forward.call_args.kwargs


class TestOpenAIModelsServiceAccount:
    def test_models_endpoint_returns_allowlist_for_service_account(self, test_client):
        sa = _sa_context(["kiro/claude-sonnet-4", "openai/gpt-5"])

        with patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=sa)):
            response = test_client.get(
                "/v1/models",
                headers={"Authorization": "Bearer izisa_testtoken"},
            )

        assert response.status_code == 200
        model_ids = {m["id"] for m in response.json()["data"]}
        assert model_ids == {"kiro/claude-sonnet-4", "openai/gpt-5"}

    def test_models_endpoint_returns_empty_list_for_empty_allowlist(self, test_client):
        sa = _sa_context([])

        with patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=sa)):
            response = test_client.get(
                "/v1/models",
                headers={"Authorization": "Bearer izisa_testtoken"},
            )

        assert response.status_code == 200
        assert response.json()["data"] == []


# ---------------------------------------------------------------------------
# Route-level enforcement — Anthropic /v1/messages
# ---------------------------------------------------------------------------

class TestAnthropicMessagesServiceAccountEnforcement:
    def test_allowed_model_forwards_to_nine_router_with_override_disabled(self, test_client):
        sa = _sa_context(["kiro/claude-sonnet-4"])
        mock_forward = AsyncMock(return_value=MagicMock(status_code=200))

        with (
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=sa)),
            patch("kiro.routes_anthropic.forward_to_nine_router", mock_forward),
        ):
            test_client.post(
                "/v1/messages",
                headers={"x-api-key": "izisa_testtoken"},
                json={
                    "model": "claude-sonnet-4",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        mock_forward.assert_called_once()
        assert mock_forward.call_args.kwargs["apply_override"] is False
        assert mock_forward.call_args.kwargs["on_usage"] is not None

    def test_disallowed_model_returns_403_anthropic_shaped_error(self, test_client):
        sa = _sa_context(["kiro/claude-sonnet-4"])
        mock_forward = AsyncMock()

        with (
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=sa)),
            patch("kiro.routes_anthropic.forward_to_nine_router", mock_forward),
        ):
            response = test_client.post(
                "/v1/messages",
                headers={"x-api-key": "izisa_testtoken"},
                json={
                    "model": "openai/gpt-5",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        assert response.status_code == 403
        body = response.json()
        assert body["type"] == "error"
        assert body["error"]["type"] == "permission_error"
        assert "not permitted" in body["error"]["message"]
        mock_forward.assert_not_called()

    def test_empty_allowlist_returns_403(self, test_client):
        sa = _sa_context([])
        mock_forward = AsyncMock()

        with (
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=sa)),
            patch("kiro.routes_anthropic.forward_to_nine_router", mock_forward),
        ):
            response = test_client.post(
                "/v1/messages",
                headers={"x-api-key": "izisa_testtoken"},
                json={
                    "model": "kiro/claude-sonnet-4",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        assert response.status_code == 403
        mock_forward.assert_not_called()


# ---------------------------------------------------------------------------
# Revoked / disabled service-account keys must be rejected outright
#
# Regression test for a bug found only by running the real gateway: a revoked
# key kept working. resolve_service_account() correctly returns None for a
# revoked key, a deactivated account, or a forged token — but the auth
# dependencies then fell through to the API_KEY_MODE branch, which accepts ANY
# bearer token, so the dead izisa_ key was silently reclassified as a valid
# opaque Kiro key. Revocation had no effect at all.
#
# The shared `test_client` fixture forces API_KEY_MODE=False, which is why the
# original unit tests could not see this. Production runs with API_KEY_MODE=true
# (.env), so these tests patch it back on.
# ---------------------------------------------------------------------------

class TestRevokedServiceAccountKeyRejected:
    def test_openai_rejects_unresolvable_service_account_token(self, test_client):
        with (
            patch("kiro.routes_openai.API_KEY_MODE", True),
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=None)),
        ):
            response = test_client.get(
                "/v1/models",
                headers={"Authorization": "Bearer izisa_revoked"},
            )

        assert response.status_code == 401

    def test_openai_chat_rejects_unresolvable_service_account_token(self, test_client):
        mock_forward = AsyncMock(return_value=MagicMock(status_code=200))

        with (
            patch("kiro.routes_openai.API_KEY_MODE", True),
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=None)),
            patch("kiro.routes_openai.forward_to_nine_router", mock_forward),
        ):
            response = test_client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer izisa_revoked"},
                json={"model": "kiro/claude-sonnet-4", "messages": [{"role": "user", "content": "Hi"}]},
            )

        assert response.status_code == 401
        mock_forward.assert_not_called()

    def test_anthropic_rejects_unresolvable_service_account_token(self, test_client):
        mock_forward = AsyncMock(return_value=MagicMock(status_code=200))

        with (
            patch("kiro.routes_anthropic.API_KEY_MODE", True),
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=None)),
            patch("kiro.routes_anthropic.forward_to_nine_router", mock_forward),
        ):
            response = test_client.post(
                "/v1/messages",
                headers={"x-api-key": "izisa_revoked"},
                json={
                    "model": "kiro/claude-sonnet-4",
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
            )

        assert response.status_code == 401
        mock_forward.assert_not_called()

    def test_ordinary_kiro_token_still_accepted_in_api_key_mode(self, test_client):
        """The rejection must be scoped to our own prefix — existing Kiro-key
        clients must keep working, since the feature is soft-deprecated only."""
        with (
            patch("kiro.routes_openai.API_KEY_MODE", True),
            patch("kiro.service_accounts.resolve_service_account", AsyncMock(return_value=None)),
        ):
            response = test_client.get(
                "/v1/models",
                headers={"Authorization": "Bearer some-ordinary-kiro-key"},
            )

        assert response.status_code != 401
