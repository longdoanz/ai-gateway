"""
Unit tests for the Service Account feature (data layer + admin CRUD API).

Covers:
- kiro/db/repositories.py: create/list/get/update/delete, key issuance/revoke,
  usage increments, and the allowed_models JSON encode/decode helpers.
- kiro/dashboard/routes_service_accounts.py: the admin CRUD endpoints.

Mirrors the mocked-session style already used in tests/unit/test_repositories.py
(no real database — SQLAlchemy statements are inspected via .compile()).
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from kiro.db.repositories import (
    SERVICE_ACCOUNT_KEY_PREFIX,
    create_service_account,
    create_service_account_key,
    decode_allowed_models,
    delete_service_account,
    encode_allowed_models,
    generate_service_account_key,
    get_service_account_by_id,
    get_service_account_key_by_hash,
    hash_api_key,
    increment_service_account_daily_usage,
    increment_service_account_usage,
    revoke_service_account_key,
    update_service_account,
)


# ---------------------------------------------------------------------------
# allowed_models JSON round trip — fail-closed semantics
# ---------------------------------------------------------------------------

class TestAllowedModelsJson:
    def test_round_trips_a_list(self):
        models = ["kiro/claude-sonnet-4", "openai/gpt-5"]
        assert decode_allowed_models(encode_allowed_models(models)) == models

    def test_empty_list_encodes_to_empty_json_array(self):
        assert encode_allowed_models([]) == "[]"

    def test_none_encodes_to_empty_json_array(self):
        assert encode_allowed_models(None) == "[]"

    def test_none_raw_decodes_to_empty_list_fail_closed(self):
        assert decode_allowed_models(None) == []

    def test_blank_raw_decodes_to_empty_list_fail_closed(self):
        assert decode_allowed_models("") == []

    def test_malformed_json_decodes_to_empty_list_fail_closed(self):
        assert decode_allowed_models("{not valid json") == []

    def test_non_list_json_decodes_to_empty_list_fail_closed(self):
        # A malformed/tampered column value that is valid JSON but not a list
        # must still fail closed rather than raise or grant blanket access.
        assert decode_allowed_models('{"not": "a list"}') == []

    def test_coerces_non_string_entries_to_strings(self):
        assert decode_allowed_models("[1, 2]") == ["1", "2"]


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

class TestServiceAccountKeyGeneration:
    def test_prefix_is_izisa(self):
        assert SERVICE_ACCOUNT_KEY_PREFIX == "izisa_"

    def test_generated_key_starts_with_prefix(self):
        assert generate_service_account_key().startswith("izisa_")

    def test_generated_keys_are_unique(self):
        keys = {generate_service_account_key() for _ in range(20)}
        assert len(keys) == 20

    def test_generated_key_length_is_sufficient(self):
        key = generate_service_account_key()
        assert len(key) > len(SERVICE_ACCOUNT_KEY_PREFIX) + 20


# ---------------------------------------------------------------------------
# create_service_account_key — raw key shown once, only hash persisted
# ---------------------------------------------------------------------------

class TestCreateServiceAccountKey:
    @pytest.mark.asyncio
    async def test_returns_raw_key_and_stores_only_hash(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        key, raw_key = await create_service_account_key(session, service_account_id=7)

        assert raw_key.startswith("izisa_")
        session.add.assert_called_once()
        added = session.add.call_args[0][0]

        # Only the hash is persisted — never the raw key material.
        assert added.key_hash == hash_api_key(raw_key)
        assert not hasattr(added, "raw_key")
        assert not hasattr(added, "key_encrypted")
        assert added.key_prefix == raw_key[:10]
        assert added.key_suffix == raw_key[-4:]
        assert added.service_account_id == 7
        session.commit.assert_called_once()
        session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_each_call_generates_a_distinct_key(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        _, raw_key_1 = await create_service_account_key(session, service_account_id=1)
        _, raw_key_2 = await create_service_account_key(session, service_account_id=1)

        assert raw_key_1 != raw_key_2


# ---------------------------------------------------------------------------
# revoke_service_account_key
# ---------------------------------------------------------------------------

class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class TestRevokeServiceAccountKey:
    @pytest.mark.asyncio
    async def test_revokes_existing_key(self):
        session = AsyncMock()
        key = SimpleNamespace(id=5, service_account_id=1, is_active=True)
        session.execute = AsyncMock(return_value=_ScalarResult(key))
        session.commit = AsyncMock()

        result = await revoke_service_account_key(session, service_account_id=1, key_id=5)

        assert result is True
        assert key.is_active is False
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_key_not_found(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_ScalarResult(None))
        session.commit = AsyncMock()

        result = await revoke_service_account_key(session, service_account_id=1, key_id=999)

        assert result is False
        session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# get_service_account_key_by_hash — requires both key and account active
# ---------------------------------------------------------------------------

class TestGetServiceAccountKeyByHash:
    @pytest.mark.asyncio
    async def test_builds_join_query_filtering_on_both_active_flags(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_ScalarResult(None))

        await get_service_account_key_by_hash(session, key_hash="abc123")

        session.execute.assert_called_once()
        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert "service_account_keys" in compiled
        assert "service_accounts" in compiled
        assert "abc123" in compiled


# ---------------------------------------------------------------------------
# Service account CRUD (mocked session)
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class TestServiceAccountCrud:
    @pytest.mark.asyncio
    async def test_create_service_account_encodes_allowed_models(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        await create_service_account(
            session,
            name="ci-bot",
            description="CI pipeline",
            allowed_models=["kiro/claude-sonnet-4"],
            created_by_user_id=1,
        )

        added = session.add.call_args[0][0]
        assert added.name == "ci-bot"
        assert added.description == "CI pipeline"
        assert added.allowed_models == '["kiro/claude-sonnet-4"]'
        assert added.created_by_user_id == 1

    @pytest.mark.asyncio
    async def test_create_service_account_defaults_to_fail_closed_empty_allowlist(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        await create_service_account(session, name="no-models-yet")

        added = session.add.call_args[0][0]
        assert added.allowed_models == "[]"

    @pytest.mark.asyncio
    async def test_get_service_account_by_id_queries_by_id(self):
        session = AsyncMock()
        sa = SimpleNamespace(id=3, name="x")
        session.execute = AsyncMock(return_value=_ScalarResult(sa))

        result = await get_service_account_by_id(session, 3)

        assert result is sa

    @pytest.mark.asyncio
    async def test_update_service_account_encodes_allowed_models_list(self):
        session = AsyncMock()
        sa = SimpleNamespace(id=1, name="ci-bot")
        session.execute = AsyncMock(side_effect=[None, _ScalarResult(sa)])
        session.commit = AsyncMock()

        await update_service_account(session, 1, allowed_models=["a", "b"])

        assert session.execute.call_count == 2
        update_stmt = session.execute.call_args_list[0][0][0]
        compiled = str(update_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert '["a", "b"]' in compiled
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_service_account_with_no_fields_is_a_noop_read(self):
        session = AsyncMock()
        sa = SimpleNamespace(id=1, name="ci-bot")
        session.execute = AsyncMock(return_value=_ScalarResult(sa))
        session.commit = AsyncMock()

        result = await update_service_account(session, 1)

        assert result is sa
        session.commit.assert_not_called()
        session.execute.assert_called_once()  # only the final get, no UPDATE issued

    @pytest.mark.asyncio
    async def test_delete_service_account_deactivates_account_and_its_keys(self):
        session = AsyncMock()
        sa = SimpleNamespace(id=1, is_active=True)
        session.execute = AsyncMock(side_effect=[_ScalarResult(sa), None])
        session.commit = AsyncMock()

        result = await delete_service_account(session, 1)

        assert result is True
        assert sa.is_active is False
        deactivate_keys_stmt = session.execute.call_args_list[1][0][0]
        compiled = str(deactivate_keys_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False})).upper()
        assert "SERVICE_ACCOUNT_KEYS" in compiled
        assert "UPDATE" in compiled
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_service_account_returns_false_when_missing(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_ScalarResult(None))
        session.commit = AsyncMock()

        result = await delete_service_account(session, 999)

        assert result is False
        session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Usage increments — accumulate, not overwrite
# ---------------------------------------------------------------------------

class TestServiceAccountUsageIncrements:
    @pytest.mark.asyncio
    async def test_increment_service_account_usage_accumulates(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        await increment_service_account_usage(session, service_account_id=1, month="2026-09", amount=3)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))
        assert "service_account_usage" in compiled
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment_service_account_daily_usage_accumulates(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        await increment_service_account_daily_usage(
            session, service_account_id=1, date="2026-09-17", input_tokens=100, output_tokens=42, model="kiro/claude-sonnet-4"
        )

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))
        assert "service_account_daily_usage" in compiled
        assert "input_tokens" in compiled
        session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Admin API routes (calling endpoint functions directly, mocked session)
# ---------------------------------------------------------------------------

def _fake_service_account(**overrides):
    defaults = dict(
        id=1,
        name="ci-bot",
        description=None,
        is_active=True,
        allowed_models="[]",
        created_by_user_id=1,
        created_at=datetime(2026, 9, 17),
        keys=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestServiceAccountRoutes:
    @pytest.mark.asyncio
    async def test_create_conflicts_on_duplicate_name(self):
        from kiro.dashboard.routes_service_accounts import create_service_account_endpoint
        from kiro.dashboard.schemas import ServiceAccountCreate

        session = AsyncMock()
        admin = MagicMock(id=1)
        body = ServiceAccountCreate(name="ci-bot", allowed_models=[])

        with patch(
            "kiro.dashboard.routes_service_accounts.get_service_account_by_name",
            AsyncMock(return_value=_fake_service_account()),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_service_account_endpoint(body, admin=admin, session=session)

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_returns_key_and_model_counts(self):
        from kiro.dashboard.routes_service_accounts import create_service_account_endpoint
        from kiro.dashboard.schemas import ServiceAccountCreate

        session = AsyncMock()
        admin = MagicMock(id=1)
        body = ServiceAccountCreate(name="ci-bot", allowed_models=["kiro/claude-sonnet-4"])
        created = _fake_service_account(allowed_models='["kiro/claude-sonnet-4"]', keys=[SimpleNamespace(id=1)])

        with (
            patch("kiro.dashboard.routes_service_accounts.get_service_account_by_name", AsyncMock(return_value=None)),
            patch("kiro.dashboard.routes_service_accounts.create_service_account", AsyncMock(return_value=created)),
        ):
            response = await create_service_account_endpoint(body, admin=admin, session=session)

        assert response.allowed_models == ["kiro/claude-sonnet-4"]
        assert response.allowed_model_count == 1
        assert response.key_count == 1

    @pytest.mark.asyncio
    async def test_update_returns_404_when_missing(self):
        from kiro.dashboard.routes_service_accounts import update_service_account_endpoint
        from kiro.dashboard.schemas import ServiceAccountUpdate

        session = AsyncMock()
        admin = MagicMock(id=1)

        with patch("kiro.dashboard.routes_service_accounts.get_service_account_by_id", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await update_service_account_endpoint(999, ServiceAccountUpdate(is_active=False), admin=admin, session=session)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_returns_404_when_missing(self):
        from kiro.dashboard.routes_service_accounts import delete_service_account_endpoint

        session = AsyncMock()
        admin = MagicMock(id=1)

        with patch("kiro.dashboard.routes_service_accounts.delete_service_account", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc_info:
                await delete_service_account_endpoint(999, admin=admin, session=session)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_issue_key_returns_raw_key_once(self):
        from kiro.dashboard.routes_service_accounts import issue_service_account_key

        session = AsyncMock()
        admin = MagicMock(id=1)
        existing = _fake_service_account()
        new_key = SimpleNamespace(
            id=10, service_account_id=1, key_prefix="izisa_abc", key_suffix="wxyz", is_active=True, created_at=datetime(2026, 9, 17)
        )

        with (
            patch("kiro.dashboard.routes_service_accounts.get_service_account_by_id", AsyncMock(return_value=existing)),
            patch(
                "kiro.dashboard.routes_service_accounts.create_service_account_key",
                AsyncMock(return_value=(new_key, "izisa_rawvalue")),
            ),
        ):
            response = await issue_service_account_key(1, admin=admin, session=session)

        assert response.raw_key == "izisa_rawvalue"
        assert response.key_prefix == "izisa_abc"

    @pytest.mark.asyncio
    async def test_issue_key_returns_404_when_account_missing(self):
        from kiro.dashboard.routes_service_accounts import issue_service_account_key

        session = AsyncMock()
        admin = MagicMock(id=1)

        with patch("kiro.dashboard.routes_service_accounts.get_service_account_by_id", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await issue_service_account_key(999, admin=admin, session=session)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_key_returns_404_when_not_found(self):
        from kiro.dashboard.routes_service_accounts import revoke_service_account_key_endpoint

        session = AsyncMock()
        admin = MagicMock(id=1)

        with patch("kiro.dashboard.routes_service_accounts.revoke_service_account_key", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc_info:
                await revoke_service_account_key_endpoint(1, 999, admin=admin, session=session)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_usage_endpoint_returns_monthly_and_daily(self):
        from kiro.dashboard.routes_service_accounts import get_service_account_usage

        session = AsyncMock()
        admin = MagicMock(id=1)
        existing = _fake_service_account()
        monthly = [SimpleNamespace(month="2026-09", current_usage=5, last_used_at=None)]
        daily = [SimpleNamespace(date="2026-09-17", model="kiro/claude-sonnet-4", input_tokens=10, output_tokens=20)]

        with (
            patch("kiro.dashboard.routes_service_accounts.get_service_account_by_id", AsyncMock(return_value=existing)),
            patch("kiro.dashboard.routes_service_accounts.get_service_account_usage_history", AsyncMock(return_value=monthly)),
            patch("kiro.dashboard.routes_service_accounts.get_service_account_daily_usage", AsyncMock(return_value=daily)),
        ):
            response = await get_service_account_usage(1, days=30, admin=admin, session=session)

        assert len(response.monthly) == 1
        assert response.monthly[0].month == "2026-09"
        assert len(response.daily) == 1
        assert response.daily[0].model == "kiro/claude-sonnet-4"
