# Usage Management Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement database layer, usage tracking engine, fallback routing, and Dashboard API for the Credit Management system integrated into Kiro Gateway.

**Architecture:** PostgreSQL-only (no Redis), SQLAlchemy 2.0 async + Alembic, in-process asyncio background tasks, JWT auth for dashboard. Single async worker model. Backward compatible — opt-in when `DATABASE_URL` is set.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, python-jose (JWT), passlib (bcrypt), cryptography (Fernet), python-multipart

---

### Task 1: Install Dependencies & Config

**Files:**
- Modify: `requirements.txt`
- Modify: `kiro/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add new dependencies to requirements.txt**

```
sqlalchemy[asyncio]>=2.0
asyncpg>=0.29
alembic>=1.13
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7
cryptography>=42.0
python-multipart>=0.0.9
```

Append these lines after the existing production dependencies (after `tiktoken`).

- [ ] **Step 2: Add new ENV vars to config.py**

Add a new section after the `WebSearch Settings` section in `kiro/config.py`:

```python
# ==================================================================================================
# Usage Management Database Settings
# ==================================================================================================

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
JWT_SECRET: str = os.getenv("JWT_SECRET", "")
JWT_ACCESS_EXPIRY: int = int(os.getenv("JWT_ACCESS_EXPIRY", "900"))
JWT_REFRESH_EXPIRY: int = int(os.getenv("JWT_REFRESH_EXPIRY", "604800"))
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
USAGE_SYNC_INTERVAL: int = int(os.getenv("USAGE_SYNC_INTERVAL", "600"))
```

- [ ] **Step 3: Update .env.example**

Add to `.env.example`:

```
# === Usage Management (optional, enables dashboard + usage tracking) ===
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/kiro_gateway
# ENCRYPTION_KEY=           # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# JWT_SECRET=               # Any random string
# JWT_ACCESS_EXPIRY=900     # 15 minutes
# JWT_REFRESH_EXPIRY=604800 # 7 days
# ADMIN_USERNAME=admin
# ADMIN_PASSWORD=changeme
# USAGE_SYNC_INTERVAL=600   # Sync usage limits every 10 minutes (seconds)
```

- [ ] **Step 4: Install dependencies locally**

Run: `pip install sqlalchemy[asyncio] asyncpg alembic "python-jose[cryptography]" "passlib[bcrypt]" cryptography python-multipart`

- [ ] **Step 5: Verify import works**

Run: `python -c "import sqlalchemy; import asyncpg; import jose; import passlib; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt kiro/config.py .env.example
git commit -m "feat(usage-mgmt): add dependencies and config for usage management"
```

---

### Task 2: Database Engine & Session

**Files:**
- Create: `kiro/db/__init__.py`
- Create: `kiro/db/engine.py`

- [ ] **Step 1: Create kiro/db/__init__.py**

```python
from kiro.db.engine import get_session, init_db, close_db, engine

__all__ = ["get_session", "init_db", "close_db", "engine"]
```

- [ ] **Step 2: Create kiro/db/engine.py**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from kiro.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=5, max_overflow=10) if DATABASE_URL else None

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False) if engine else None


async def get_session():
    if async_session_factory is None:
        raise RuntimeError("Database not configured (DATABASE_URL is empty)")
    async with async_session_factory() as session:
        yield session


async def init_db():
    if engine is None:
        return
    from kiro.db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    if engine is not None:
        await engine.dispose()
```

- [ ] **Step 3: Verify module imports**

Run: `python -c "from kiro.db.engine import engine; print('engine:', engine)"`
Expected: `engine: None` (no DATABASE_URL set)

- [ ] **Step 4: Commit**

```bash
git add kiro/db/
git commit -m "feat(usage-mgmt): add database engine and session factory"
```

---

### Task 3: SQLAlchemy ORM Models

**Files:**
- Create: `kiro/db/models.py`

- [ ] **Step 1: Create kiro/db/models.py**

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="owner", lazy="selectin")


class KiroUserMapping(Base):
    __tablename__ = "kiro_user_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kiro_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_active_id", "is_active", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    kiro_user_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("kiro_user_mappings.kiro_user_id"), nullable=True)
    key_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    key_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_suffix: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    owner: Mapped["User"] = relationship("User", back_populates="api_keys")
    usages: Mapped[list["KeyUsage"]] = relationship("KeyUsage", back_populates="api_key", lazy="selectin")


class KeyUsage(Base):
    __tablename__ = "key_usage"
    __table_args__ = (
        UniqueConstraint("key_id", "month", name="uq_key_usage_key_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_id: Mapped[int] = mapped_column(Integer, ForeignKey("api_keys.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    current_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    api_key: Mapped["ApiKey"] = relationship("ApiKey", back_populates="usages")


class SystemConfig(Base):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
```

- [ ] **Step 2: Verify models load**

Run: `python -c "from kiro.db.models import User, ApiKey, KeyUsage, KiroUserMapping, SystemConfig; print('5 models loaded')"`
Expected: `5 models loaded`

- [ ] **Step 3: Commit**

```bash
git add kiro/db/models.py
git commit -m "feat(usage-mgmt): add SQLAlchemy ORM models for 5 tables"
```

---

### Task 4: Alembic Setup & Initial Migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/` (directory)

- [ ] **Step 1: Initialize Alembic**

Run: `cd /data/longdt/kiro-gateway && alembic init alembic`

- [ ] **Step 2: Edit alembic.ini — set sqlalchemy.url to empty (will be overridden by env.py)**

In `alembic.ini`, change:
```
sqlalchemy.url = driver://user:pass@localhost/dbname
```
to:
```
sqlalchemy.url =
```

- [ ] **Step 3: Replace alembic/env.py with async version**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from kiro.config import DATABASE_URL
from kiro.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = DATABASE_URL or config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    url = DATABASE_URL or config.get_main_option("sqlalchemy.url")
    connectable = create_async_engine(url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4: Generate initial migration**

Run: `alembic revision --autogenerate -m "initial schema: users, api_keys, key_usage, kiro_user_mappings, system_config"`

Verify the generated file in `alembic/versions/` contains CREATE TABLE for all 5 tables.

- [ ] **Step 5: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat(usage-mgmt): add Alembic setup and initial migration"
```

---

### Task 5: Repositories (Data Access Layer)

**Files:**
- Create: `kiro/db/repositories.py`

- [ ] **Step 1: Create kiro/db/repositories.py**

```python
import hashlib
from datetime import datetime

from cryptography.fernet import Fernet
from passlib.context import CryptContext
from sqlalchemy import select, update, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.config import ENCRYPTION_KEY
from kiro.db.models import ApiKey, KeyUsage, KiroUserMapping, SystemConfig, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_fernet = Fernet(ENCRYPTION_KEY.encode()) if ENCRYPTION_KEY else None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def encrypt_api_key(key: str) -> str:
    if _fernet is None:
        raise RuntimeError("ENCRYPTION_KEY not configured")
    return _fernet.encrypt(key.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    if _fernet is None:
        raise RuntimeError("ENCRYPTION_KEY not configured")
    return _fernet.decrypt(encrypted.encode()).decode()


def mask_key(key: str) -> tuple[str, str]:
    return key[:10] if len(key) > 10 else key[:4], key[-4:]


# --- User ---

async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.id))
    return list(result.scalars().all())


async def create_user(session: AsyncSession, username: str, password: str, role: str = "user") -> User:
    user = User(username=username, password_hash=hash_password(password), role=role)
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


async def list_api_keys(session: AsyncSession, user_id: int | None = None) -> list[ApiKey]:
    stmt = select(ApiKey).order_by(ApiKey.id)
    if user_id is not None:
        stmt = stmt.where(ApiKey.user_id == user_id)
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
    stmt = pg_insert(KeyUsage).values(key_id=key_id, month=month, current_usage=amount, last_used_at=datetime.utcnow())
    stmt = stmt.on_conflict_on_constraint("uq_key_usage_key_month").do_update(
        set_={"current_usage": KeyUsage.current_usage + amount, "last_used_at": datetime.utcnow()}
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


async def upsert_usage_limits(session: AsyncSession, key_id: int, month: str, usage_limit: int, current_usage: int) -> None:
    stmt = pg_insert(KeyUsage).values(
        key_id=key_id, month=month, usage_limit=usage_limit, current_usage=current_usage, last_synced_at=datetime.utcnow()
    )
    stmt = stmt.on_conflict_on_constraint("uq_key_usage_key_month").do_update(
        set_={"usage_limit": usage_limit, "current_usage": current_usage, "last_synced_at": datetime.utcnow()}
    )
    await session.execute(stmt)
    await session.commit()


# --- KiroUserMapping ---

async def upsert_kiro_user_mappings(session: AsyncSession, mappings: list[dict]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for m in mappings:
        stmt = pg_insert(KiroUserMapping).values(
            kiro_user_id=m["kiro_user_id"], email=m.get("email"), username=m.get("username")
        )
        stmt = stmt.on_conflict_on_constraint("kiro_user_mappings_kiro_user_id_key").do_update(
            set_={"email": m.get("email"), "username": m.get("username"), "imported_at": datetime.utcnow()}
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
    stmt = stmt.on_conflict_on_constraint("system_config_pkey").do_update(set_={"value": value, "updated_at": datetime.utcnow()})
    await session.execute(stmt)
    await session.commit()


async def get_all_config(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(SystemConfig))
    return {row.key: row.value for row in result.scalars().all()}
```

- [ ] **Step 2: Verify repository imports**

Run: `python -c "from kiro.db.repositories import hash_api_key, mask_key; print(mask_key('sk-proj-abcdefghijklmnop1234')); print(hash_api_key('test'))"`
Expected: `('sk-proj-abc', '1234')` and a SHA256 hex string.

- [ ] **Step 3: Commit**

```bash
git add kiro/db/repositories.py
git commit -m "feat(usage-mgmt): add repository layer for all DB operations"
```

---

### Task 6: JWT Auth & Dashboard Dependencies

**Files:**
- Create: `kiro/dashboard/__init__.py`
- Create: `kiro/dashboard/jwt_auth.py`
- Create: `kiro/dashboard/deps.py`

- [ ] **Step 1: Create kiro/dashboard/__init__.py**

```python
from fastapi import APIRouter

dashboard_router = APIRouter(prefix="/api", tags=["dashboard"])
```

- [ ] **Step 2: Create kiro/dashboard/jwt_auth.py**

```python
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from kiro.config import JWT_SECRET, JWT_ACCESS_EXPIRY, JWT_REFRESH_EXPIRY

ALGORITHM = "HS256"


def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(seconds=JWT_ACCESS_EXPIRY)
    payload = {"sub": str(user_id), "role": role, "exp": expire, "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(seconds=JWT_REFRESH_EXPIRY)
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
```

- [ ] **Step 3: Create kiro/dashboard/deps.py**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.jwt_auth import decode_token
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import get_user_by_id

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> User:
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = await get_user_by_id(session, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
```

- [ ] **Step 4: Verify imports**

Run: `python -c "from kiro.dashboard.deps import get_current_user, require_admin; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add kiro/dashboard/
git commit -m "feat(usage-mgmt): add JWT auth and dashboard dependencies"
```

---

### Task 7: Dashboard Pydantic Schemas

**Files:**
- Create: `kiro/dashboard/schemas.py`

- [ ] **Step 1: Create kiro/dashboard/schemas.py**

```python
from datetime import datetime
from pydantic import BaseModel, Field


# --- Auth ---

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# --- User ---

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserUpdate(BaseModel):
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6)
    role: str | None = Field(default=None, pattern="^(admin|user)$")


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserDetailResponse(UserResponse):
    api_keys: list["ApiKeyResponse"] = []


# --- ApiKey ---

class ApiKeyCreate(BaseModel):
    raw_key: str = Field(min_length=10)


class ApiKeyResponse(BaseModel):
    id: int
    user_id: int
    kiro_user_id: str | None = None
    key_prefix: str
    key_suffix: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyToggle(BaseModel):
    is_active: bool


# --- KeyUsage ---

class KeyUsageResponse(BaseModel):
    month: str
    current_usage: int
    usage_limit: int
    last_synced_at: datetime | None = None
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


# --- Overview ---

class DailyUsage(BaseModel):
    date: str
    credits: int


class OverviewResponse(BaseModel):
    total_credits_used: int
    total_credits_limit: int
    active_users: int
    active_keys: int
    daily_usage: list[DailyUsage]


# --- Config ---

class SystemConfigResponse(BaseModel):
    enable_model_override: bool = False
    enforced_global_model: str = "auto"
    enable_usage_sharing: bool = False


class SystemConfigUpdate(BaseModel):
    enable_model_override: bool | None = None
    enforced_global_model: str | None = None
    enable_usage_sharing: bool | None = None


# --- Import ---

class ImportResult(BaseModel):
    imported: int
    updated: int
    errors: list[str]
```

- [ ] **Step 2: Verify schemas**

Run: `python -c "from kiro.dashboard.schemas import LoginRequest, UserResponse, OverviewResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add kiro/dashboard/schemas.py
git commit -m "feat(usage-mgmt): add Pydantic schemas for dashboard API"
```

---

### Task 8: Auth Routes (Login & Refresh)

**Files:**
- Create: `kiro/dashboard/routes_auth.py`

- [ ] **Step 1: Create kiro/dashboard/routes_auth.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.jwt_auth import create_access_token, create_refresh_token, decode_token
from kiro.dashboard.schemas import LoginRequest, RefreshRequest, TokenResponse
from kiro.db.engine import get_session
from kiro.db.repositories import get_user_by_id, get_user_by_username, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await get_user_by_username(session, body.username)
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = await get_user_by_id(session, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )
```

- [ ] **Step 2: Verify route imports**

Run: `python -c "from kiro.dashboard.routes_auth import router; print(len(router.routes), 'routes')"`
Expected: `2 routes`

- [ ] **Step 3: Commit**

```bash
git add kiro/dashboard/routes_auth.py
git commit -m "feat(usage-mgmt): add auth routes (login, refresh)"
```

---

### Task 9: User Management Routes

**Files:**
- Create: `kiro/dashboard/routes_users.py`

- [ ] **Step 1: Create kiro/dashboard/routes_users.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import require_admin, get_current_user
from kiro.dashboard.schemas import UserCreate, UserDetailResponse, UserResponse, UserUpdate
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import create_user, get_user_by_id, get_user_by_username, list_users, update_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def get_users(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return await list_users(session)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_new_user(body: UserCreate, admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    existing = await get_user_by_username(session, body.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    return await create_user(session, body.username, body.password, body.role)


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user(user_id: int, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if caller.role != "admin" and caller.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_existing_user(user_id: int, body: UserUpdate, admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    user = await update_user(session, user_id, **updates)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
```

- [ ] **Step 2: Verify**

Run: `python -c "from kiro.dashboard.routes_users import router; print(len(router.routes), 'routes')"`
Expected: `4 routes`

- [ ] **Step 3: Commit**

```bash
git add kiro/dashboard/routes_users.py
git commit -m "feat(usage-mgmt): add user management routes"
```

---

### Task 10: API Key Management Routes

**Files:**
- Create: `kiro/dashboard/routes_keys.py`

- [ ] **Step 1: Create kiro/dashboard/routes_keys.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user, require_admin
from kiro.dashboard.schemas import ApiKeyCreate, ApiKeyResponse, ApiKeyToggle, KeyUsageResponse
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import (
    create_api_key,
    get_api_key_by_hash,
    get_all_usage_for_month,
    get_usage_for_month,
    hash_api_key,
    list_api_keys,
    update_api_key,
)

router = APIRouter(prefix="/keys", tags=["keys"])


@router.get("", response_model=list[ApiKeyResponse])
async def get_keys(caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    user_id = None if caller.role == "admin" else caller.id
    return await list_api_keys(session, user_id=user_id)


@router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def register_key(body: ApiKeyCreate, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    existing = await get_api_key_by_hash(session, hash_api_key(body.raw_key))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This API key is already registered")
    return await create_api_key(session, caller.id, body.raw_key)


@router.put("/{key_id}", response_model=ApiKeyResponse)
async def toggle_key(key_id: int, body: ApiKeyToggle, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    keys = await list_api_keys(session, user_id=None if caller.role == "admin" else caller.id)
    key = next((k for k in keys if k.id == key_id), None)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    await update_api_key(session, key_id, is_active=body.is_active)
    key.is_active = body.is_active
    return key


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_key(key_id: int, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    keys = await list_api_keys(session, user_id=None if caller.role == "admin" else caller.id)
    key = next((k for k in keys if k.id == key_id), None)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    await update_api_key(session, key_id, is_active=False)


@router.get("/{key_id}/usage", response_model=list[KeyUsageResponse])
async def get_key_usage(key_id: int, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    keys = await list_api_keys(session, user_id=None if caller.role == "admin" else caller.id)
    key = next((k for k in keys if k.id == key_id), None)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    from sqlalchemy import select
    from kiro.db.models import KeyUsage
    result = await session.execute(select(KeyUsage).where(KeyUsage.key_id == key_id).order_by(KeyUsage.month.desc()))
    return list(result.scalars().all())
```

- [ ] **Step 2: Verify**

Run: `python -c "from kiro.dashboard.routes_keys import router; print(len(router.routes), 'routes')"`
Expected: `5 routes`

- [ ] **Step 3: Commit**

```bash
git add kiro/dashboard/routes_keys.py
git commit -m "feat(usage-mgmt): add API key management routes"
```

---

### Task 11: Overview / KPI Route

**Files:**
- Create: `kiro/dashboard/routes_overview.py`

- [ ] **Step 1: Create kiro/dashboard/routes_overview.py**

```python
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user
from kiro.dashboard.schemas import DailyUsage, OverviewResponse
from kiro.db.engine import get_session
from kiro.db.models import ApiKey, KeyUsage, User

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("", response_model=OverviewResponse)
async def get_overview(caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    current_month = datetime.utcnow().strftime("%Y-%m")

    # Total credits used & limit this month
    usage_result = await session.execute(
        select(
            func.coalesce(func.sum(KeyUsage.current_usage), 0),
            func.coalesce(func.sum(KeyUsage.usage_limit), 0),
        ).where(KeyUsage.month == current_month)
    )
    total_used, total_limit = usage_result.one()

    # Active users & keys
    active_users = (await session.execute(select(func.count()).where(User.is_active == True))).scalar_one()
    active_keys = (await session.execute(select(func.count()).where(ApiKey.is_active == True))).scalar_one()

    # Daily usage for last 30 days (from key_usage.last_used_at grouped by date)
    # Simplified: return per-month data split into daily placeholder
    # Real daily tracking would need a separate daily_usage table — for now aggregate monthly
    daily_usage = [DailyUsage(date=current_month, credits=int(total_used))]

    return OverviewResponse(
        total_credits_used=int(total_used),
        total_credits_limit=int(total_limit),
        active_users=active_users,
        active_keys=active_keys,
        daily_usage=daily_usage,
    )
```

- [ ] **Step 2: Verify**

Run: `python -c "from kiro.dashboard.routes_overview import router; print(len(router.routes), 'routes')"`
Expected: `1 routes`

- [ ] **Step 3: Commit**

```bash
git add kiro/dashboard/routes_overview.py
git commit -m "feat(usage-mgmt): add overview/KPI route"
```

---

### Task 12: System Config Routes

**Files:**
- Create: `kiro/dashboard/routes_config.py`

- [ ] **Step 1: Create kiro/dashboard/routes_config.py**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import require_admin
from kiro.dashboard.schemas import SystemConfigResponse, SystemConfigUpdate
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import get_all_config, set_config

router = APIRouter(prefix="/config", tags=["config"])

CONFIG_DEFAULTS = {
    "enable_model_override": "false",
    "enforced_global_model": "auto",
    "enable_usage_sharing": "false",
}


def _to_response(raw: dict[str, str]) -> SystemConfigResponse:
    merged = {**CONFIG_DEFAULTS, **raw}
    return SystemConfigResponse(
        enable_model_override=merged["enable_model_override"].lower() == "true",
        enforced_global_model=merged["enforced_global_model"],
        enable_usage_sharing=merged["enable_usage_sharing"].lower() == "true",
    )


@router.get("", response_model=SystemConfigResponse)
async def get_config_route(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    raw = await get_all_config(session)
    return _to_response(raw)


@router.put("", response_model=SystemConfigResponse)
async def update_config_route(body: SystemConfigUpdate, admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        str_value = str(value).lower() if isinstance(value, bool) else str(value)
        await set_config(session, key, str_value)
    raw = await get_all_config(session)
    return _to_response(raw)
```

- [ ] **Step 2: Verify**

Run: `python -c "from kiro.dashboard.routes_config import router; print(len(router.routes), 'routes')"`
Expected: `2 routes`

- [ ] **Step 3: Commit**

```bash
git add kiro/dashboard/routes_config.py
git commit -m "feat(usage-mgmt): add system config routes"
```

---

### Task 13: User Import Route

**Files:**
- Create: `kiro/dashboard/routes_import.py`

- [ ] **Step 1: Create kiro/dashboard/routes_import.py**

```python
import csv
import io
import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import require_admin
from kiro.dashboard.schemas import ImportResult
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import upsert_kiro_user_mappings

router = APIRouter(prefix="/import", tags=["import"])

REQUIRED_FIELDS = {"kiro_user_id"}
OPTIONAL_FIELDS = {"email", "username"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


@router.post("/users", response_model=ImportResult)
async def import_users(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large (max 5MB)")

    content = await file.read()
    text = content.decode("utf-8-sig")
    errors: list[str] = []
    mappings: list[dict] = []

    filename = file.filename or ""
    if filename.endswith(".json"):
        try:
            data = json.loads(text)
            if not isinstance(data, list):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON must be an array of objects")
            for i, row in enumerate(data):
                if "kiro_user_id" not in row:
                    errors.append(f"Row {i}: missing kiro_user_id")
                    continue
                mappings.append({"kiro_user_id": row["kiro_user_id"], "email": row.get("email"), "username": row.get("username")})
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON: {e}")
    else:
        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader):
            if "kiro_user_id" not in row or not row["kiro_user_id"]:
                errors.append(f"Row {i + 1}: missing kiro_user_id")
                continue
            mappings.append({"kiro_user_id": row["kiro_user_id"], "email": row.get("email"), "username": row.get("username")})

    if not mappings:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid mappings found in file")

    inserted, updated = await upsert_kiro_user_mappings(session, mappings)
    return ImportResult(imported=inserted, updated=updated, errors=errors)
```

- [ ] **Step 2: Verify**

Run: `python -c "from kiro.dashboard.routes_import import router; print(len(router.routes), 'routes')"`
Expected: `1 routes`

- [ ] **Step 3: Commit**

```bash
git add kiro/dashboard/routes_import.py
git commit -m "feat(usage-mgmt): add user import route (CSV/JSON)"
```

---

### Task 14: Usage Cache

**Files:**
- Create: `kiro/usage/__init__.py`
- Create: `kiro/usage/usage_cache.py`

- [ ] **Step 1: Create kiro/usage/__init__.py**

```python
```

- [ ] **Step 2: Create kiro/usage/usage_cache.py**

```python
import asyncio
from dataclasses import dataclass

from loguru import logger


@dataclass
class UsageEntry:
    key_id: int
    current_usage: int
    usage_limit: int
    is_active: bool


class UsageCache:
    def __init__(self):
        self._cache: dict[int, UsageEntry] = {}
        self._lock = asyncio.Lock()

    async def load_from_db(self, session) -> None:
        from kiro.db.models import ApiKey, KeyUsage
        from sqlalchemy import select
        from datetime import datetime

        current_month = datetime.utcnow().strftime("%Y-%m")

        keys_result = await session.execute(select(ApiKey))
        keys = {k.id: k for k in keys_result.scalars().all()}

        usage_result = await session.execute(select(KeyUsage).where(KeyUsage.month == current_month))
        usage_map = {u.key_id: u for u in usage_result.scalars().all()}

        async with self._lock:
            self._cache.clear()
            for key_id, key in keys.items():
                usage = usage_map.get(key_id)
                self._cache[key_id] = UsageEntry(
                    key_id=key_id,
                    current_usage=usage.current_usage if usage else 0,
                    usage_limit=usage.usage_limit if usage else 0,
                    is_active=key.is_active,
                )
        logger.info(f"UsageCache loaded: {len(self._cache)} keys")

    async def get(self, key_id: int) -> UsageEntry | None:
        return self._cache.get(key_id)

    async def increment(self, key_id: int, amount: int = 1) -> None:
        async with self._lock:
            entry = self._cache.get(key_id)
            if entry:
                entry.current_usage += amount

    async def refresh_limits(self, updates: dict[int, tuple[int, int]]) -> None:
        async with self._lock:
            for key_id, (usage_limit, current_usage) in updates.items():
                entry = self._cache.get(key_id)
                if entry:
                    entry.usage_limit = usage_limit
                    entry.current_usage = current_usage

    def get_available_keys(self, exclude_key_id: int | None = None) -> list[int]:
        available = []
        for key_id, entry in self._cache.items():
            if not entry.is_active:
                continue
            if key_id == exclude_key_id:
                continue
            if entry.usage_limit <= 0:
                continue
            remaining_ratio = (entry.usage_limit - entry.current_usage) / entry.usage_limit
            if remaining_ratio > 0.01:
                available.append(key_id)
        return available

    def set_key_active(self, key_id: int, is_active: bool) -> None:
        entry = self._cache.get(key_id)
        if entry:
            entry.is_active = is_active


usage_cache = UsageCache()
```

- [ ] **Step 3: Verify**

Run: `python -c "from kiro.usage.usage_cache import usage_cache, UsageEntry; print(type(usage_cache))"`
Expected: `<class 'kiro.usage.usage_cache.UsageCache'>`

- [ ] **Step 4: Commit**

```bash
git add kiro/usage/
git commit -m "feat(usage-mgmt): add in-memory usage cache"
```

---

### Task 15: Usage Tracker

**Files:**
- Create: `kiro/usage/tracker.py`

- [ ] **Step 1: Create kiro/usage/tracker.py**

```python
from datetime import datetime

from loguru import logger

from kiro.db.engine import async_session_factory
from kiro.db.repositories import increment_usage
from kiro.usage.usage_cache import usage_cache


async def track_usage(key_id: int, credits_used: int | None = None) -> None:
    amount = credits_used if credits_used is not None and credits_used > 0 else 1
    month = datetime.utcnow().strftime("%Y-%m")

    try:
        if async_session_factory is None:
            return
        async with async_session_factory() as session:
            await increment_usage(session, key_id, month, amount)
        await usage_cache.increment(key_id, amount)
        logger.debug(f"Tracked {amount} credits for key_id={key_id} month={month}")
    except Exception as e:
        logger.error(f"Failed to track usage for key_id={key_id}: {e}")


def extract_credits_from_response(response_data: dict | bytes | None) -> int | None:
    if response_data is None:
        return None
    if isinstance(response_data, bytes):
        try:
            import json
            response_data = json.loads(response_data)
        except Exception:
            return None
    if isinstance(response_data, dict):
        breakdown = response_data.get("usageBreakdownList") or response_data.get("usageBreakdown") or []
        if isinstance(breakdown, list):
            for item in breakdown:
                if isinstance(item, dict) and "currentUsage" in item:
                    return int(item["currentUsage"])
        credits = response_data.get("creditsUsed") or response_data.get("credits_used")
        if credits is not None:
            return int(credits)
    return None
```

- [ ] **Step 2: Verify**

Run: `python -c "from kiro.usage.tracker import extract_credits_from_response; print(extract_credits_from_response({'creditsUsed': 5}))"`
Expected: `5`

- [ ] **Step 3: Commit**

```bash
git add kiro/usage/tracker.py
git commit -m "feat(usage-mgmt): add usage tracker with credit extraction"
```

---

### Task 16: Fallback Router

**Files:**
- Create: `kiro/usage/fallback.py`

- [ ] **Step 1: Create kiro/usage/fallback.py**

```python
import asyncio

from loguru import logger

from kiro.db.engine import async_session_factory
from kiro.db.repositories import decrypt_api_key, get_all_config
from kiro.usage.usage_cache import usage_cache


class NoAvailableKeyError(Exception):
    pass


class FallbackRouter:
    def __init__(self):
        self._counter = 0
        self._lock = asyncio.Lock()

    async def _is_sharing_enabled(self) -> bool:
        if async_session_factory is None:
            return False
        async with async_session_factory() as session:
            config = await get_all_config(session)
        return config.get("enable_usage_sharing", "false").lower() == "true"

    async def pre_check(self, current_key_id: int) -> tuple[int, str] | None:
        if not await self._is_sharing_enabled():
            return None

        entry = await usage_cache.get(current_key_id)
        if entry is None or entry.usage_limit <= 0:
            return None

        remaining_ratio = (entry.usage_limit - entry.current_usage) / entry.usage_limit
        if remaining_ratio >= 0.01:
            return None

        logger.info(f"Key {current_key_id} at {remaining_ratio:.1%} remaining, triggering fallback")
        return await self._pick_fallback_key(current_key_id)

    async def post_check(self, current_key_id: int) -> tuple[int, str] | None:
        if not await self._is_sharing_enabled():
            return None
        logger.info(f"Key {current_key_id} got 429, triggering fallback")
        return await self._pick_fallback_key(current_key_id)

    async def _pick_fallback_key(self, exclude_key_id: int) -> tuple[int, str]:
        available = usage_cache.get_available_keys(exclude_key_id=exclude_key_id)
        if not available:
            raise NoAvailableKeyError("No available keys with remaining quota")

        async with self._lock:
            idx = self._counter % len(available)
            self._counter += 1

        picked_key_id = available[idx]

        if async_session_factory is None:
            raise NoAvailableKeyError("Database not configured")
        from kiro.db.models import ApiKey
        from sqlalchemy import select
        async with async_session_factory() as session:
            result = await session.execute(select(ApiKey.key_encrypted).where(ApiKey.id == picked_key_id))
            encrypted = result.scalar_one_or_none()
        if encrypted is None:
            raise NoAvailableKeyError(f"Key {picked_key_id} not found in DB")

        raw_key = decrypt_api_key(encrypted)
        logger.info(f"Fallback: switched from key {exclude_key_id} to key {picked_key_id}")
        return picked_key_id, raw_key


fallback_router = FallbackRouter()
```

- [ ] **Step 2: Verify**

Run: `python -c "from kiro.usage.fallback import fallback_router, NoAvailableKeyError; print(type(fallback_router))"`
Expected: `<class 'kiro.usage.fallback.FallbackRouter'>`

- [ ] **Step 3: Commit**

```bash
git add kiro/usage/fallback.py
git commit -m "feat(usage-mgmt): add fallback router with round-robin key selection"
```

---

### Task 17: Sync Worker

**Files:**
- Create: `kiro/usage/sync_worker.py`

- [ ] **Step 1: Create kiro/usage/sync_worker.py**

```python
import asyncio

from loguru import logger

from kiro.config import REGION, USAGE_SYNC_INTERVAL
from kiro.db.engine import async_session_factory
from kiro.db.models import ApiKey
from kiro.db.repositories import decrypt_api_key, upsert_usage_limits, update_api_key
from kiro.usage.usage_cache import usage_cache


async def sync_usage_limits() -> None:
    if async_session_factory is None:
        return

    from kiro.api_key_mode import get_usage_limits, build_api_key_headers
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.is_active == True))
        active_keys = list(result.scalars().all())

    logger.info(f"Sync worker: syncing usage limits for {len(active_keys)} active keys")
    cache_updates: dict[int, tuple[int, int]] = {}

    for key in active_keys:
        try:
            raw_key = decrypt_api_key(key.key_encrypted)
            data = await get_usage_limits(raw_key, resource_type="CREDIT")

            breakdown_list = data.get("usageBreakdownList", [])
            if not breakdown_list:
                continue

            credit_entry = None
            for entry in breakdown_list:
                if entry.get("resourceType") == "CREDIT":
                    credit_entry = entry
                    break
            if credit_entry is None:
                credit_entry = breakdown_list[0]

            usage_limit = int(credit_entry.get("usageLimit", 0))
            current_usage_precise = credit_entry.get("currentUsageWithPrecision")
            current_usage = int(current_usage_precise) if current_usage_precise is not None else int(credit_entry.get("currentUsage", 0))

            from datetime import datetime
            month = datetime.utcnow().strftime("%Y-%m")

            async with async_session_factory() as session:
                await upsert_usage_limits(session, key.id, month, usage_limit, current_usage)

            cache_updates[key.id] = (usage_limit, current_usage)

            # Update kiro_user_id mapping if available
            user_info = data.get("userInfo", {})
            kiro_user_id = user_info.get("userId")
            if kiro_user_id and kiro_user_id != key.kiro_user_id:
                async with async_session_factory() as session:
                    await update_api_key(session, key.id, kiro_user_id=kiro_user_id)

            logger.debug(f"Synced key {key.id}: usage={current_usage}/{usage_limit}")

        except Exception as e:
            logger.warning(f"Sync worker: failed to sync key {key.id}: {e}")
            continue

    if cache_updates:
        await usage_cache.refresh_limits(cache_updates)
        logger.info(f"Sync worker: refreshed cache for {len(cache_updates)} keys")


async def run_sync_loop() -> None:
    while True:
        try:
            await sync_usage_limits()
        except asyncio.CancelledError:
            logger.info("Sync worker: cancelled")
            break
        except Exception as e:
            logger.error(f"Sync worker: unexpected error: {e}")
        await asyncio.sleep(USAGE_SYNC_INTERVAL)
```

- [ ] **Step 2: Verify**

Run: `python -c "from kiro.usage.sync_worker import run_sync_loop; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add kiro/usage/sync_worker.py
git commit -m "feat(usage-mgmt): add sync worker for periodic usage limits refresh"
```

---

### Task 18: Scheduler (Lifespan Integration)

**Files:**
- Create: `kiro/usage/scheduler.py`

- [ ] **Step 1: Create kiro/usage/scheduler.py**

```python
import asyncio

from loguru import logger

from kiro.config import DATABASE_URL
from kiro.db.engine import async_session_factory, init_db, close_db
from kiro.db.repositories import create_user, get_user_by_username
from kiro.usage.usage_cache import usage_cache
from kiro.usage.sync_worker import run_sync_loop


_sync_task: asyncio.Task | None = None


def is_db_configured() -> bool:
    return bool(DATABASE_URL)


async def startup() -> None:
    global _sync_task

    if not is_db_configured():
        logger.info("Usage management: DATABASE_URL not set, skipping init")
        return

    await init_db()
    logger.info("Usage management: database initialized")

    # Seed admin user if configured and not exists
    from kiro.config import ADMIN_USERNAME, ADMIN_PASSWORD
    if ADMIN_USERNAME and ADMIN_PASSWORD:
        async with async_session_factory() as session:
            existing = await get_user_by_username(session, ADMIN_USERNAME)
            if existing is None:
                await create_user(session, ADMIN_USERNAME, ADMIN_PASSWORD, role="admin")
                logger.info(f"Usage management: created initial admin user '{ADMIN_USERNAME}'")

    # Load usage cache
    async with async_session_factory() as session:
        await usage_cache.load_from_db(session)

    # Start sync worker
    _sync_task = asyncio.create_task(run_sync_loop())
    logger.info("Usage management: sync worker started")


async def shutdown() -> None:
    global _sync_task

    if not is_db_configured():
        return

    if _sync_task is not None:
        _sync_task.cancel()
        try:
            await _sync_task
        except asyncio.CancelledError:
            pass
        logger.info("Usage management: sync worker stopped")

    await close_db()
    logger.info("Usage management: database closed")
```

- [ ] **Step 2: Verify**

Run: `python -c "from kiro.usage.scheduler import is_db_configured; print('configured:', is_db_configured())"`
Expected: `configured: False`

- [ ] **Step 3: Commit**

```bash
git add kiro/usage/scheduler.py
git commit -m "feat(usage-mgmt): add scheduler for lifespan integration"
```

---

### Task 19: Integrate into main.py (Lifespan + Router Mount)

**Files:**
- Modify: `main.py`
- Modify: `kiro/dashboard/__init__.py`

- [ ] **Step 1: Update kiro/dashboard/__init__.py to register all sub-routers**

```python
from fastapi import APIRouter

from kiro.dashboard.routes_auth import router as auth_router
from kiro.dashboard.routes_users import router as users_router
from kiro.dashboard.routes_keys import router as keys_router
from kiro.dashboard.routes_overview import router as overview_router
from kiro.dashboard.routes_config import router as config_router
from kiro.dashboard.routes_import import router as import_router

dashboard_router = APIRouter(prefix="/api", tags=["dashboard"])
dashboard_router.include_router(auth_router)
dashboard_router.include_router(users_router)
dashboard_router.include_router(keys_router)
dashboard_router.include_router(overview_router)
dashboard_router.include_router(config_router)
dashboard_router.include_router(import_router)
```

- [ ] **Step 2: Add usage management imports to main.py**

Add after the existing imports (after `from kiro.debug_middleware import DebugLoggerMiddleware`):

```python
from kiro.usage.scheduler import is_db_configured, startup as usage_startup, shutdown as usage_shutdown
```

- [ ] **Step 3: Add usage management startup to lifespan function**

In the `lifespan` function in `main.py`, add after `logger.info("Model resolver initialized")` and before `yield`:

```python
    # --- Usage Management (opt-in when DATABASE_URL is set) ---
    if is_db_configured():
        await usage_startup()
        from kiro.dashboard import dashboard_router
        app.include_router(dashboard_router)
        logger.info("Usage management: dashboard API mounted at /api/")
```

- [ ] **Step 4: Add usage management shutdown to lifespan function**

In the `lifespan` function, add before the existing `await app.state.http_client.aclose()`:

```python
    # Shutdown usage management
    if is_db_configured():
        await usage_shutdown()
```

- [ ] **Step 5: Verify app starts without DATABASE_URL**

Run: `python -c "from main import app; print('App created, routes:', len(app.routes))"`
Expected: App creates successfully, no usage management routes loaded.

- [ ] **Step 6: Commit**

```bash
git add main.py kiro/dashboard/__init__.py
git commit -m "feat(usage-mgmt): integrate usage management into app lifespan"
```

---

### Task 20: Proxy Integration (Fallback + Tracking in api_key_mode.py)

**Files:**
- Modify: `kiro/api_key_mode.py`

This is the most sensitive task — modifying the existing proxy flow. Changes must be minimal and guarded by `is_db_configured()`.

- [ ] **Step 1: Add imports at top of api_key_mode.py**

Add after the existing imports (after `from kiro.utils import get_machine_fingerprint`):

```python
from kiro.usage.scheduler import is_db_configured
```

- [ ] **Step 2: Add helper to resolve key_id from token**

Add after the `build_api_key_headers` function:

```python
async def _resolve_key_id(token: str) -> int | None:
    if not is_db_configured():
        return None
    from kiro.db.engine import async_session_factory
    from kiro.db.repositories import get_api_key_by_hash, hash_api_key
    try:
        async with async_session_factory() as session:
            api_key = await get_api_key_by_hash(session, hash_api_key(token))
            return api_key.id if api_key else None
    except Exception:
        return None


async def _try_fallback_pre_check(token: str, key_id: int | None) -> tuple[str, int | None] | None:
    if key_id is None or not is_db_configured():
        return None
    try:
        from kiro.usage.fallback import fallback_router
        result = await fallback_router.pre_check(key_id)
        if result:
            new_key_id, new_raw_key = result
            return new_raw_key, new_key_id
    except Exception as e:
        logger.debug(f"Fallback pre-check failed: {e}")
    return None


async def _track_usage_background(key_id: int | None, credits: int | None) -> None:
    if key_id is None or not is_db_configured():
        return
    try:
        from kiro.usage.tracker import track_usage
        await track_usage(key_id, credits)
    except Exception as e:
        logger.debug(f"Usage tracking failed: {e}")
```

- [ ] **Step 3: Integrate into handle_chat_openai**

In `handle_chat_openai`, after `token = get_api_key_from_request(request)`, add:

```python
    key_id = await _resolve_key_id(token)

    # Fallback pre-check: swap key if current one is near quota
    fallback_result = await _try_fallback_pre_check(token, key_id)
    if fallback_result:
        token, key_id = fallback_result[0], fallback_result[1]
```

In the streaming `stream_wrapper` function, before the `finally:` block (after the stream completes), add tracking. Replace the `finally:` block:

```python
                finally:
                    await _track_usage_background(key_id, None)
                    await http_client.close()
```

In the non-streaming branch, after `openai_response = await collect_stream_response(...)`, add:

```python
            await _track_usage_background(key_id, None)
```

- [ ] **Step 4: Integrate into handle_chat_anthropic**

Same pattern as Step 3. After `raw_token` is extracted, add:

```python
    key_id = await _resolve_key_id(raw_token)

    fallback_result = await _try_fallback_pre_check(raw_token, key_id)
    if fallback_result:
        raw_token, key_id = fallback_result[0], fallback_result[1]
```

In the streaming `finally:` block:

```python
                finally:
                    await _track_usage_background(key_id, None)
                    await http_client.close()
```

In the non-streaming branch, after `anthropic_response = await collect_anthropic_response(...)`:

```python
            await _track_usage_background(key_id, None)
```

- [ ] **Step 5: Verify app still starts and proxy works without DB**

Run: `python -c "from kiro.api_key_mode import handle_chat_openai, handle_chat_anthropic; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add kiro/api_key_mode.py
git commit -m "feat(usage-mgmt): integrate fallback routing and usage tracking into proxy"
```

---

### Task 21: Docker Compose Update

**Files:**
- Modify: `docker-compose.apikey.yml`

- [ ] **Step 1: Add PostgreSQL service to docker-compose.apikey.yml**

Add a `postgres` service and update `kiro-gateway-apikey` to depend on it:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: kiro_gateway
      POSTGRES_USER: kiro
      POSTGRES_PASSWORD: kiro_secret
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U kiro -d kiro_gateway"]
      interval: 5s
      timeout: 3s
      retries: 5

  kiro-gateway-apikey:
    # ... existing config ...
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      # ... existing env vars ...
      DATABASE_URL: postgresql+asyncpg://kiro:kiro_secret@postgres:5432/kiro_gateway
      ENCRYPTION_KEY: ${ENCRYPTION_KEY:-}
      JWT_SECRET: ${JWT_SECRET:-change-me-in-production}
      ADMIN_USERNAME: ${ADMIN_USERNAME:-admin}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:-changeme}

volumes:
  pgdata:
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.apikey.yml
git commit -m "feat(usage-mgmt): add PostgreSQL to docker-compose"
```
