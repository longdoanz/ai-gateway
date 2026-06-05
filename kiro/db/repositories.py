import hashlib
import re
from datetime import datetime, timezone

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

from cryptography.fernet import Fernet
import bcrypt
from sqlalchemy import select, update, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.config import ENCRYPTION_KEY
from kiro.db.models import ApiKey, DailyCreditSnapshot, DailyUsage, FallbackUsage, GatewayKey, GatewayKeyDailyUsage, GatewayKeyUsage, KeyUsage, KiroUserMapping, SystemConfig, User


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


async def _cache_key_hash(key_h: str, key_id: int) -> None:
    try:
        from kiro.usage.token_cache import token_cache
        await token_cache.set(key_h, key_id)
    except Exception:
        pass


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
    can_create_gateway_key: bool = False,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        google_id=google_id,
        email=email,
        can_create_gateway_key=can_create_gateway_key,
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
        await _cache_key_hash(key_h, existing.id)
        return existing, False

    prefix, suffix = mask_key(raw_key)
    stmt = pg_insert(ApiKey).values(
        user_id=default_user_id,
        key_hash=key_h,
        key_encrypted=encrypt_api_key(raw_key),
        key_prefix=prefix,
        key_suffix=suffix,
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["key_hash"])
    result = await session.execute(stmt)
    await session.commit()

    if result.rowcount == 0:
        existing = await get_api_key_by_hash(session, key_h)
        if existing:
            await _cache_key_hash(key_h, existing.id)
            return existing, False

    api_key = await get_api_key_by_hash(session, key_h)
    await _cache_key_hash(key_h, api_key.id)
    return api_key, True


async def list_api_keys(session: AsyncSession, user_id: int | None = None, limit: int = 50, offset: int = 0) -> list[ApiKey]:
    stmt = select(ApiKey).where(ApiKey.is_system == False, ApiKey.is_deleted == False).order_by(ApiKey.id)
    if user_id is not None:
        stmt = stmt.where(ApiKey.user_id == user_id)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_active_api_keys(session: AsyncSession) -> list[ApiKey]:
    result = await session.execute(select(ApiKey).where(ApiKey.is_active == True).order_by(ApiKey.id))
    return list(result.scalars().all())


async def create_api_key(
    session: AsyncSession,
    user_id: int | None,
    raw_key: str,
    is_system: bool = False,
    use_proxy: bool = False,
) -> ApiKey:
    prefix, suffix = mask_key(raw_key)
    key_hash = hash_api_key(raw_key)
    key_encrypted = encrypt_api_key(raw_key)

    # For system keys: reactivate existing (possibly soft-deleted) record if hash matches.
    # Hash is preserved on soft delete for system keys specifically to allow this.
    if is_system:
        existing = await get_api_key_by_hash(session, key_hash)
        if existing:
            await session.execute(
                update(ApiKey).where(ApiKey.id == existing.id).values(
                    key_encrypted=key_encrypted,
                    key_prefix=prefix,
                    key_suffix=suffix,
                    is_active=True,
                    is_deleted=False,
                    is_system=True,
                    use_proxy=use_proxy,
                )
            )
            await session.commit()
            await session.refresh(existing)
            await _cache_key_hash(key_hash, existing.id)
            try:
                from kiro.usage.usage_cache import usage_cache
                usage_cache.upsert_key(existing.id, is_active=True, is_system=True, use_proxy=use_proxy)
            except Exception:
                pass
            return existing

    if user_id is not None:
        result = await session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.id)
        )
        existing_keys = list(result.scalars().all())

        if existing_keys:
            api_key = existing_keys[0]
            await session.execute(
                update(ApiKey).where(ApiKey.id == api_key.id).values(
                    key_hash=key_hash,
                    key_encrypted=key_encrypted,
                    key_prefix=prefix,
                    key_suffix=suffix,
                    is_active=True,
                    is_system=is_system,
                    use_proxy=use_proxy,
                )
            )

            if len(existing_keys) > 1:
                from sqlalchemy import delete
                duplicate_ids = [key.id for key in existing_keys[1:]]
                await session.execute(delete(KeyUsage).where(KeyUsage.key_id.in_(duplicate_ids)))
                await session.execute(delete(DailyUsage).where(DailyUsage.key_id.in_(duplicate_ids)))
                await session.execute(delete(FallbackUsage).where(
                    (FallbackUsage.original_key_id.in_(duplicate_ids)) | (FallbackUsage.fallback_key_id.in_(duplicate_ids))
                ))
                await session.execute(delete(ApiKey).where(ApiKey.id.in_(duplicate_ids)))

            await session.commit()
            await session.refresh(api_key)
            await _cache_key_hash(key_hash, api_key.id)

            try:
                from kiro.usage.usage_cache import usage_cache
                usage_cache.upsert_key(api_key.id, is_active=True, is_system=is_system, use_proxy=use_proxy)
                for dup_id in duplicate_ids:
                    usage_cache.remove_key(dup_id)
            except Exception:
                pass

            return api_key

    # New key (System Key or User Key without existing)
    api_key = ApiKey(
        user_id=user_id,
        key_hash=key_hash,
        key_encrypted=key_encrypted,
        key_prefix=prefix,
        key_suffix=suffix,
        is_active=True,
        is_system=is_system,
        use_proxy=use_proxy,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    await _cache_key_hash(key_hash, api_key.id)

    try:
        from kiro.usage.usage_cache import usage_cache
        usage_cache.upsert_key(api_key.id, is_active=True, is_system=is_system, use_proxy=use_proxy)
    except Exception:
        pass

    return api_key


async def update_api_key(session: AsyncSession, key_id: int, **kwargs) -> None:
    await session.execute(update(ApiKey).where(ApiKey.id == key_id).values(**kwargs))
    await session.commit()
    try:
        from kiro.usage.token_cache import token_cache
        await token_cache.invalidate_by_key_id(key_id)
        if 'key_hash' in kwargs:
            await token_cache.set(kwargs['key_hash'], key_id)
    except Exception:
        pass


async def delete_api_key(session: AsyncSession, key_id: int) -> bool:
    import secrets
    gk = await session.get(ApiKey, key_id)
    if gk is None:
        return False

    # Soft delete: deactivate and preserve analytics records.
    # For user keys: rotate hash so the raw key can never auth again.
    # For system keys: keep hash intact so the same key can be re-registered later (reactivation).
    gk.is_active = False
    gk.is_deleted = True
    if not gk.is_system:
        gk.key_hash = secrets.token_hex(32)

    # Nullify the pool-key reference in gateway usage so gateway analytics
    # don't break if the pool key is gone.
    await session.execute(
        update(GatewayKeyUsage).where(GatewayKeyUsage.key_id == key_id).values(key_id=None)
    )
    await session.execute(
        update(GatewayKeyDailyUsage).where(GatewayKeyDailyUsage.key_id == key_id).values(key_id=None)
    )

    await session.commit()

    try:
        from kiro.usage.usage_cache import usage_cache
        usage_cache.remove_key(key_id)
    except Exception:
        pass

    try:
        from kiro.usage.token_cache import token_cache
        await token_cache.invalidate_by_key_id(key_id)
    except Exception:
        pass

    return True


async def merge_duplicate_keys_for_user(session: AsyncSession, keep_key_id: int, kiro_user_id: str) -> tuple[int, list[int]]:
    """Refresh the chosen key for a kiro user without deleting any keys.

    The caller still gets back the key id that should be treated as the
    preferred record for subsequent usage updates, but all matching keys are
    left in place.

    Returns (survivor_key_id, deleted_key_ids). The deleted list is always
    empty now."""

    result = await session.execute(
        select(ApiKey).where(ApiKey.kiro_user_id == kiro_user_id).order_by(ApiKey.id)
    )
    all_keys = list(result.scalars().all())
    if len(all_keys) <= 1:
        return keep_key_id, []

    # Prefer the caller-provided keep_key_id as the survivor when it exists among the keys.
    survivor = next((k for k in all_keys if k.id == keep_key_id), None)
    if survivor is None:
        survivor = all_keys[0]

    # No update is performed here to avoid UNIQUE constraint violations on key_hash.
    # The system supports multiple active keys per user, and usage is aggregated
    # via get_canonical_usage_key_id().
    
    return survivor.id, []


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


async def increment_daily_usage(session: AsyncSession, key_id: int, date: str, input_tokens: int = 0, output_tokens: int = 0, model: str = "unknown") -> None:
    stmt = pg_insert(DailyUsage).values(key_id=key_id, date=date, model=model, input_tokens=input_tokens, output_tokens=output_tokens)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_daily_usage_key_date_model",
        set_={"input_tokens": DailyUsage.input_tokens + input_tokens, "output_tokens": DailyUsage.output_tokens + output_tokens},
    )
    await session.execute(stmt)
    await session.commit()


async def increment_fallback_usage(
    session: AsyncSession, original_key_id: int, fallback_key_id: int, month: str, input_tokens: int = 0, output_tokens: int = 0, model: str = "unknown"
) -> None:
    stmt = pg_insert(FallbackUsage).values(
        original_key_id=original_key_id, fallback_key_id=fallback_key_id, month=month, model=model, input_tokens=input_tokens, output_tokens=output_tokens
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_fallback_usage_orig_fb_month_model",
        set_={"input_tokens": FallbackUsage.input_tokens + input_tokens, "output_tokens": FallbackUsage.output_tokens + output_tokens},
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


# --- DailyCreditSnapshot ---

async def upsert_daily_credit_snapshot(session: AsyncSession, kiro_user_id: str, date_str: str, current_usage: int) -> None:
    stmt = pg_insert(DailyCreditSnapshot).values(
        kiro_user_id=kiro_user_id, date=date_str, current_usage=current_usage
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_credit_snapshot_user_date",
        set_={"current_usage": text("GREATEST(daily_credit_snapshots.current_usage, EXCLUDED.current_usage)")},
    )
    await session.execute(stmt)
    await session.commit()


async def get_credit_snapshots(session: AsyncSession, start_date: str, end_date: str) -> list[tuple[str, int]]:
    """Returns list of (date, total_current_usage) aggregated across all users."""
    from sqlalchemy import func
    result = await session.execute(
        select(DailyCreditSnapshot.date, func.sum(DailyCreditSnapshot.current_usage).label("total"))
        .where(DailyCreditSnapshot.date >= start_date, DailyCreditSnapshot.date <= end_date)
        .group_by(DailyCreditSnapshot.date)
        .order_by(DailyCreditSnapshot.date)
    )
    return [(row.date, int(row.total)) for row in result.all()]


# --- KiroUserMapping ---

async def list_kiro_user_mappings(session: AsyncSession, limit: int = 50, offset: int = 0) -> list[KiroUserMapping]:
    result = await session.execute(select(KiroUserMapping).order_by(KiroUserMapping.kiro_user_id).limit(limit).offset(offset))
    return list(result.scalars().all())

def normalize_kiro_user_id(value: str) -> str:
    """Strip 'd-xxx.' prefix if present, e.g. 'd-abc123.john' -> 'john'."""
    return re.sub(r"^d-[^.]*\.", "", value)


async def build_kiro_email_lookup(session: AsyncSession) -> dict[str, str]:
    """Build a lookup dict: normalized kiro_user_id -> email. Exact keys are also included."""
    result = await session.execute(
        select(KiroUserMapping.kiro_user_id, KiroUserMapping.email).where(KiroUserMapping.email.isnot(None))
    )
    lookup: dict[str, str] = {}
    for kiro_uid, email in result.all():
        lookup[kiro_uid] = email
        normalized = normalize_kiro_user_id(kiro_uid)
        if normalized != kiro_uid:
            lookup[normalized] = email
    return lookup


def resolve_kiro_email(kiro_user_id: str, lookup: dict[str, str]) -> str | None:
    """Resolve email for a kiro_user_id using exact match first, then normalized match."""
    if kiro_user_id in lookup:
        return lookup[kiro_user_id]
    normalized = normalize_kiro_user_id(kiro_user_id)
    return lookup.get(normalized)


async def upsert_kiro_user_mappings(session: AsyncSession, mappings: list[dict]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for m in mappings:
        stmt = pg_insert(KiroUserMapping).values(
            kiro_user_id=m["kiro_user_id"], email=m.get("email"), username=m.get("username")
        )
        # Only overwrite fields that are explicitly provided; None means the
        # column was absent from the import file, so preserve the existing value.
        update_set: dict = {"imported_at": _utcnow()}
        if m.get("email") is not None:
            update_set["email"] = m["email"]
        if m.get("username") is not None:
            update_set["username"] = m["username"]
        stmt = stmt.on_conflict_do_update(
            index_elements=["kiro_user_id"],
            set_=update_set,
        )
        result = await session.execute(stmt)
        if result.rowcount == 1:
            inserted += 1
        else:
            updated += 1
    await session.commit()
    return inserted, updated


# --- GatewayKey ---

GATEWAY_KEY_PREFIX = "iziaigw_"


def generate_gateway_key() -> str:
    import secrets
    return GATEWAY_KEY_PREFIX + secrets.token_urlsafe(32)


async def get_gateway_key_by_hash(session: AsyncSession, key_hash: str) -> GatewayKey | None:
    result = await session.execute(select(GatewayKey).where(GatewayKey.key_hash == key_hash, GatewayKey.is_active == True))
    return result.scalar_one_or_none()


async def get_gateway_key_by_user_id(session: AsyncSession, user_id: int) -> GatewayKey | None:
    result = await session.execute(select(GatewayKey).where(GatewayKey.user_id == user_id, GatewayKey.is_active == True))
    return result.scalar_one_or_none()


async def create_gateway_key(session: AsyncSession, user_id: int) -> tuple[GatewayKey, str]:
    """Create or reactivate a gateway key. Returns (GatewayKey, raw_key). raw_key shown only once."""
    raw_key = generate_gateway_key()
    result = await session.execute(select(GatewayKey).where(GatewayKey.user_id == user_id))
    gk = result.scalar_one_or_none()
    if gk is not None:
        # Reuse existing record to preserve usage history; just rotate the key material.
        gk.key_hash = hash_api_key(raw_key)
        gk.key_prefix = raw_key[:10]
        gk.key_suffix = raw_key[-4:]
        gk.is_active = True
    else:
        gk = GatewayKey(
            user_id=user_id,
            key_hash=hash_api_key(raw_key),
            key_prefix=raw_key[:10],
            key_suffix=raw_key[-4:],
        )
        session.add(gk)
    await session.commit()
    await session.refresh(gk)
    return gk, raw_key


async def delete_gateway_key(session: AsyncSession, user_id: int) -> bool:
    """Soft-delete: deactivate the key so usage history is preserved."""
    import secrets
    result = await session.execute(select(GatewayKey).where(GatewayKey.user_id == user_id))
    gk = result.scalar_one_or_none()
    if gk is None:
        return False
    gk.is_active = False
    # Rotate hash so the old raw key can never authenticate again.
    gk.key_hash = secrets.token_hex(32)
    await session.commit()
    return True


async def increment_gateway_key_usage(session: AsyncSession, gateway_key_id: int, month: str, amount: int = 1, key_id: int | None = None) -> None:
    stmt = pg_insert(GatewayKeyUsage).values(
        gateway_key_id=gateway_key_id, month=month, current_usage=amount, last_used_at=_utcnow(), key_id=key_id
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_gw_key_usage_gwkey_month_poolkey",
        set_={"current_usage": GatewayKeyUsage.current_usage + amount, "last_used_at": _utcnow()},
    )
    await session.execute(stmt)
    await session.commit()


async def increment_gateway_key_daily_usage(session: AsyncSession, gateway_key_id: int, date: str, input_tokens: int = 0, output_tokens: int = 0, model: str = "unknown", key_id: int | None = None) -> None:
    stmt = pg_insert(GatewayKeyDailyUsage).values(gateway_key_id=gateway_key_id, date=date, model=model, input_tokens=input_tokens, output_tokens=output_tokens, key_id=key_id)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_gw_daily_usage_gwkey_date_poolkey_model",
        set_={"input_tokens": GatewayKeyDailyUsage.input_tokens + input_tokens, "output_tokens": GatewayKeyDailyUsage.output_tokens + output_tokens},
    )
    await session.execute(stmt)
    await session.commit()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_canonical_usage_key_id(session: AsyncSession, key_id: int) -> int:
    """Return a stable key id for usage tracking.

    If the key is mapped to a Kiro user, this resolves to the oldest key for
    that Kiro user so usage keeps flowing to the same surviving record even
    when other keys for the user are deleted or rotated.

    Args:
        session: Active async database session.
        key_id: The raw API key id seen at request time.

    Returns:
        A stable key id to use for usage writes.
    """
    result = await session.execute(select(ApiKey.kiro_user_id).where(ApiKey.id == key_id))
    kiro_user_id = result.scalar_one_or_none()
    if not kiro_user_id:
        return key_id

    result = await session.execute(
        select(ApiKey.id)
        .where(ApiKey.kiro_user_id == kiro_user_id)
        .order_by(ApiKey.id.asc())
        .limit(1)
    )
    canonical_key_id = result.scalar_one_or_none()
    return canonical_key_id or key_id


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
