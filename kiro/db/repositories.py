import hashlib
from datetime import datetime, timezone

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

from cryptography.fernet import Fernet
import bcrypt
from sqlalchemy import select, update, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.config import ENCRYPTION_KEY
from kiro.db.models import ApiKey, DailyUsage, KeyUsage, KiroUserMapping, SystemConfig, User


_fernet = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not ENCRYPTION_KEY:
            raise RuntimeError("ENCRYPTION_KEY not configured")
        _fernet = Fernet(ENCRYPTION_KEY.encode())
    return _fernet


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def encrypt_api_key(key: str) -> str:
    return _get_fernet().encrypt(key.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


def mask_key(key: str) -> tuple[str, str]:
    return key[:10] if len(key) > 10 else key[:4], key[-4:]


# --- User ---

async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_google_id(session: AsyncSession, google_id: str) -> User | None:
    result = await session.execute(select(User).where(User.google_id == google_id))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def list_users(session: AsyncSession, limit: int = 50, offset: int = 0) -> list[User]:
    result = await session.execute(select(User).order_by(User.id).limit(limit).offset(offset))
    return list(result.scalars().all())


async def create_user(
    session: AsyncSession,
    username: str,
    password: str,
    role: str = "user",
    google_id: str | None = None,
    email: str | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        google_id=google_id,
        email=email,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(session: AsyncSession, user_id: int, **kwargs) -> User | None:
    if "password" in kwargs:
        kwargs["password_hash"] = hash_password(kwargs.pop("password"))
    await session.execute(update(User).where(User.id == user_id).values(**kwargs))
    await session.commit()
    return await get_user_by_id(session, user_id)


# --- ApiKey ---

async def get_api_key_by_hash(session: AsyncSession, key_hash: str) -> ApiKey | None:
    result = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    return result.scalar_one_or_none()


async def get_or_create_api_key(session: AsyncSession, raw_key: str, default_user_id: int = 1) -> tuple[ApiKey, bool]:
    """Returns (api_key, is_new) — is_new=True when the key was just created."""
    key_h = hash_api_key(raw_key)
    existing = await get_api_key_by_hash(session, key_h)
    if existing:
        return existing, False
    prefix, suffix = mask_key(raw_key)
    api_key = ApiKey(
        user_id=default_user_id,
        key_hash=key_h,
        key_encrypted=encrypt_api_key(raw_key),
        key_prefix=prefix,
        key_suffix=suffix,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return api_key, True


async def list_api_keys(session: AsyncSession, user_id: int | None = None, limit: int = 50, offset: int = 0) -> list[ApiKey]:
    stmt = select(ApiKey).order_by(ApiKey.id)
    if user_id is not None:
        stmt = stmt.where(ApiKey.user_id == user_id)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_active_api_keys(session: AsyncSession) -> list[ApiKey]:
    result = await session.execute(select(ApiKey).where(ApiKey.is_active == True).order_by(ApiKey.id))
    return list(result.scalars().all())


async def create_api_key(session: AsyncSession, user_id: int, raw_key: str) -> ApiKey:
    prefix, suffix = mask_key(raw_key)
    api_key = ApiKey(
        user_id=user_id,
        key_hash=hash_api_key(raw_key),
        key_encrypted=encrypt_api_key(raw_key),
        key_prefix=prefix,
        key_suffix=suffix,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return api_key


async def update_api_key(session: AsyncSession, key_id: int, **kwargs) -> None:
    await session.execute(update(ApiKey).where(ApiKey.id == key_id).values(**kwargs))
    await session.commit()


# --- KeyUsage ---

async def increment_usage(session: AsyncSession, key_id: int, month: str, amount: int = 1) -> None:
    stmt = pg_insert(KeyUsage).values(key_id=key_id, month=month, current_usage=amount, last_used_at=_utcnow())
    stmt = stmt.on_conflict_do_update(
        constraint="uq_key_usage_key_month",
        set_={"current_usage": KeyUsage.current_usage + amount, "last_used_at": _utcnow()},
    )
    await session.execute(stmt)
    await session.commit()


async def get_usage_for_month(session: AsyncSession, key_id: int, month: str) -> KeyUsage | None:
    result = await session.execute(
        select(KeyUsage).where(KeyUsage.key_id == key_id, KeyUsage.month == month)
    )
    return result.scalar_one_or_none()


async def get_all_usage_for_month(session: AsyncSession, month: str) -> list[KeyUsage]:
    result = await session.execute(select(KeyUsage).where(KeyUsage.month == month))
    return list(result.scalars().all())


async def increment_daily_usage(session: AsyncSession, key_id: int, date: str, amount: int = 1) -> None:
    stmt = pg_insert(DailyUsage).values(key_id=key_id, date=date, credits=amount)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_daily_usage_key_date",
        set_={"credits": DailyUsage.credits + amount},
    )
    await session.execute(stmt)
    await session.commit()


async def get_usage_history(session: AsyncSession, key_id: int) -> list[KeyUsage]:
    result = await session.execute(
        select(KeyUsage).where(KeyUsage.key_id == key_id).order_by(KeyUsage.month.desc())
    )
    return list(result.scalars().all())


async def upsert_usage_limits(session: AsyncSession, key_id: int, month: str, usage_limit: int, current_usage: int) -> None:
    stmt = pg_insert(KeyUsage).values(
        key_id=key_id, month=month, usage_limit=usage_limit, current_usage=current_usage, last_synced_at=_utcnow()
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_key_usage_key_month",
        set_={"usage_limit": usage_limit, "current_usage": current_usage, "last_synced_at": _utcnow()},
    )
    await session.execute(stmt)
    await session.commit()


# --- KiroUserMapping ---

async def list_kiro_user_mappings(session: AsyncSession, limit: int = 50, offset: int = 0) -> list[KiroUserMapping]:
    result = await session.execute(select(KiroUserMapping).order_by(KiroUserMapping.kiro_user_id).limit(limit).offset(offset))
    return list(result.scalars().all())

async def upsert_kiro_user_mappings(session: AsyncSession, mappings: list[dict]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for m in mappings:
        stmt = pg_insert(KiroUserMapping).values(
            kiro_user_id=m["kiro_user_id"], email=m.get("email"), username=m.get("username")
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["kiro_user_id"],
            set_={"email": m.get("email"), "username": m.get("username"), "imported_at": _utcnow()},
        )
        result = await session.execute(stmt)
        if result.rowcount == 1:
            inserted += 1
        else:
            updated += 1
    await session.commit()
    return inserted, updated


# --- SystemConfig ---

async def get_config(session: AsyncSession, key: str) -> str | None:
    result = await session.execute(select(SystemConfig.value).where(SystemConfig.key == key))
    row = result.scalar_one_or_none()
    return row


async def set_config(session: AsyncSession, key: str, value: str) -> None:
    stmt = pg_insert(SystemConfig).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(
        constraint="system_config_pkey",
        set_={"value": value, "updated_at": _utcnow()},
    )
    await session.execute(stmt)
    await session.commit()


async def get_all_config(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(SystemConfig))
    return {row.key: row.value for row in result.scalars().all()}
