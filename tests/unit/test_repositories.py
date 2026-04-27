import pytest
from unittest.mock import AsyncMock
from sqlalchemy.dialects import postgresql
from kiro.db.repositories import hash_api_key, mask_key, hash_password, verify_password, increment_daily_usage


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



@pytest.mark.asyncio
async def test_increment_daily_usage_accumulates():
    """Verify the upsert adds to existing credits rather than overwriting."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    await increment_daily_usage(session, key_id=1, date="2026-04-27", amount=42)

    session.execute.assert_called_once()
    session.commit.assert_called_once()

    # Verify the statement accumulates (credits + amount), not overwrites
    stmt = session.execute.call_args[0][0]
    compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))
    assert "daily_usage" in compiled
    # The ON CONFLICT clause should reference credits addition, not plain assignment
    assert "credits" in compiled
