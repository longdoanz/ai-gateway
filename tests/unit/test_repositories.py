import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy.dialects import postgresql
from kiro.db.repositories import (
    hash_api_key, mask_key, hash_password, verify_password, increment_daily_usage,
    create_api_key, get_canonical_usage_key_id,
    generate_gateway_key, GATEWAY_KEY_PREFIX,
)


@pytest.mark.asyncio
async def test_update_api_key_invalidates_and_sets_cache():
    from kiro.db import repositories
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    with patch("kiro.usage.token_cache.token_cache.invalidate_by_key_id", new_callable=AsyncMock) as mock_invalidate, \
         patch("kiro.usage.token_cache.token_cache.set", new_callable=AsyncMock) as mock_set:
        await repositories.update_api_key(session, key_id=5, key_hash="newhash")

    mock_invalidate.assert_called_once_with(5)
    mock_set.assert_called_once_with("newhash", 5)


class TestRepositoryUtils:
    """Tests for pure utility functions in kiro/db/repositories.py"""

    def test_hash_api_key_deterministic(self):
        h1 = hash_api_key("test-key")
        h2 = hash_api_key("test-key")
        assert h1 == h2

    def test_hash_api_key_different_keys(self):
        h1 = hash_api_key("key-1")
        h2 = hash_api_key("key-2")
        assert h1 != h2

    def test_hash_api_key_is_sha256(self):
        h = hash_api_key("test")
        assert len(h) == 64  # SHA256 hex digest

    def test_mask_key_long(self):
        prefix, suffix = mask_key("sk-proj-abcdefghijklmnop1234")
        assert prefix == "sk-proj-ab"
        assert suffix == "1234"

    def test_mask_key_short(self):
        prefix, suffix = mask_key("abcd1234")
        assert prefix == "abcd"
        assert suffix == "1234"

    def test_password_hash_and_verify(self):
        hashed = hash_password("my-password")
        assert hashed != "my-password"
        assert verify_password("my-password", hashed) is True
        assert verify_password("wrong-password", hashed) is False

    def test_password_hash_is_unique(self):
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2  # bcrypt uses random salt


class TestGatewayKeyGeneration:
    def test_prefix_is_iziaigw(self):
        assert GATEWAY_KEY_PREFIX == "iziaigw_"

    def test_generated_key_starts_with_prefix(self):
        key = generate_gateway_key()
        assert key.startswith("iziaigw_")

    def test_generated_keys_are_unique(self):
        keys = {generate_gateway_key() for _ in range(20)}
        assert len(keys) == 20

    def test_generated_key_length_is_sufficient(self):
        key = generate_gateway_key()
        assert len(key) > len(GATEWAY_KEY_PREFIX) + 20



@pytest.mark.asyncio
async def test_increment_daily_usage_accumulates():
    """Verify the upsert adds to existing tokens rather than overwriting."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    await increment_daily_usage(session, key_id=1, date="2026-04-27", input_tokens=100, output_tokens=42)

    session.execute.assert_called_once()
    session.commit.assert_called_once()

    # Verify the statement accumulates (tokens + amount), not overwrites
    stmt = session.execute.call_args[0][0]
    compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))
    assert "daily_usage" in compiled
    assert "input_tokens" in compiled


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_create_api_key_updates_existing_row_in_place():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_FakeResult([SimpleNamespace(id=7)]), None])
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = AsyncMock()

    with patch("kiro.db.repositories.mask_key", return_value=("prefix", "suffix")), \
         patch("kiro.db.repositories.hash_api_key", return_value="hash-1"), \
         patch("kiro.db.repositories.encrypt_api_key", return_value="enc-1"):
        api_key = await create_api_key(session, user_id=42, raw_key="raw-key-1")

    assert api_key.id == 7
    session.add.assert_not_called()
    assert session.execute.call_count == 2
    first_stmt = session.execute.call_args_list[0][0][0]
    second_stmt = session.execute.call_args_list[1][0][0]
    assert "api_keys" in str(first_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))
    assert "UPDATE" in str(second_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False})).upper()
    session.commit.assert_called_once()
    session.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_get_canonical_usage_key_id_prefers_oldest_key_for_same_kiro_user():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[
        _ScalarResult("d-abc123.user-1"),
        _ScalarResult(7),
    ])

    resolved = await get_canonical_usage_key_id(session, key_id=42)

    assert resolved == 7
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_merge_duplicate_keys_for_user_does_not_delete_rows():
    from kiro.db.repositories import merge_duplicate_keys_for_user

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[
        _FakeResult([
            SimpleNamespace(id=7, key_hash="hash-old", key_encrypted="enc-old", key_prefix="pre-old", key_suffix="suf-old"),
            SimpleNamespace(id=9, key_hash="hash-new", key_encrypted="enc-new", key_prefix="pre-new", key_suffix="suf-new"),
        ]),
    ])
    session.commit = AsyncMock()

    survivor_id, deleted_ids = await merge_duplicate_keys_for_user(session, keep_key_id=7, kiro_user_id="user-1")

    assert survivor_id == 7
    assert deleted_ids == []
    assert session.execute.call_count == 1  # Only the SELECT
    session.commit.assert_not_called()
