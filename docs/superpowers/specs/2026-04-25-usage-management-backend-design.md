# Usage Management Backend — Design Spec

## Overview

Backend cho hệ thống Credit Management tích hợp vào Kiro Gateway. Cung cấp database layer, usage tracking, fallback routing, và Dashboard API phục vụ frontend.

**Decisions:**
- PostgreSQL only (no Redis) — atomic UPDATE cho usage tracking, single async worker model
- SQLAlchemy 2.0 async + Alembic migrations
- In-process asyncio tasks cho background jobs
- JWT authentication cho Dashboard API
- Backward compatible — opt-in khi có `DATABASE_URL`

---

## 1. Project Structure

```
kiro/
  # ─── Existing proxy (không thay đổi) ───
  config.py, auth.py, api_key_mode.py, cache.py, model_resolver.py
  routes_openai.py, routes_anthropic.py
  models_openai.py, models_anthropic.py
  converters_*.py, streaming_*.py, http_client.py
  parsers.py, thinking_parser.py, tokenizer.py, utils.py
  exceptions.py, kiro_errors.py, network_errors.py
  payload_guards.py, truncation_*.py
  debug_logger.py, debug_middleware.py, mcp_tools.py

  # ─── New: Database Layer ───
  db/
    __init__.py          # export engine, get_session
    engine.py            # async engine, sessionmaker, init_db()
    models.py            # SQLAlchemy ORM models (5 tables)
    repositories.py      # data access functions (query/insert/update)

  # ─── New: Dashboard API ───
  dashboard/
    __init__.py
    deps.py              # get_current_user, require_admin dependencies
    jwt_auth.py          # JWT create/verify, password hashing (bcrypt)
    schemas.py           # Pydantic request/response schemas
    routes_auth.py       # POST /api/auth/login, POST /api/auth/refresh
    routes_users.py      # CRUD /api/users
    routes_keys.py       # CRUD /api/keys, GET /api/keys/{id}/usage
    routes_overview.py   # GET /api/overview (dashboard KPIs)
    routes_config.py     # GET/PUT /api/config
    routes_import.py     # POST /api/import/users (CSV/JSON upload)

  # ─── New: Usage Engine ───
  usage/
    __init__.py
    tracker.py           # post-request usage increment (PG atomic)
    usage_cache.py       # in-memory cache of usage limits, loaded from PG
    fallback.py          # key pool selection, round-robin routing
    sync_worker.py       # periodic tasks: sync limits, persist counters
    scheduler.py         # lifespan integration, start/stop background loops

alembic/                 # top-level Alembic migrations
  alembic.ini
  env.py
  versions/
```

---

## 2. Database Schema

### 2.1 `users` — Dashboard accounts

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, autoincrement |
| username | str | unique, indexed |
| password_hash | str | bcrypt |
| role | str | "admin" \| "user" |
| is_active | bool | default True |
| created_at | datetime | server_default=now |

### 2.2 `kiro_user_mappings` — Import mappings (Kiro UserID to email/username)

| Column | Type | Constraints |
|---|---|---|
| id | int | PK |
| kiro_user_id | str | unique, indexed |
| email | str | nullable |
| username | str | nullable |
| imported_at | datetime | server_default=now |

### 2.3 `api_keys` — External keys (BYOK)

| Column | Type | Constraints |
|---|---|---|
| id | int | PK |
| user_id | int | FK -> users.id |
| kiro_user_id | str | nullable, FK -> kiro_user_mappings.kiro_user_id |
| key_hash | str | SHA256, indexed, dùng cho fast lookup |
| key_encrypted | str | Fernet encrypted, decrypt khi gửi request |
| key_prefix | str | e.g. "sk-proj-ax" |
| key_suffix | str | e.g. "8f92" |
| is_active | bool | default True |
| created_at | datetime | server_default=now |

Composite index: `(is_active, id)` cho fallback pool query.

### 2.4 `key_usage` — Monthly usage tracking

| Column | Type | Constraints |
|---|---|---|
| id | int | PK |
| key_id | int | FK -> api_keys.id |
| month | str | e.g. "2026-04" |
| current_usage | int | default 0, atomic increment |
| usage_limit | int | default 0, synced từ getUsageLimits |
| last_synced_at | datetime | nullable |
| last_used_at | datetime | nullable |

Unique constraint: `(key_id, month)`.

### 2.5 `system_config` — Dynamic config (admin thay đổi qua UI)

| Column | Type | Constraints |
|---|---|---|
| key | str | PK |
| value | str | |
| updated_at | datetime | |

Keys: `enable_model_override`, `enforced_global_model`, `enable_usage_sharing`.

---

## 3. Usage Engine

### 3.1 Usage Tracker (`usage/tracker.py`)

Post-request, non-blocking. Chạy trong FastAPI `BackgroundTasks` sau khi response stream hoàn tất.

- Extract `creditsUsed` từ `getAssistanceResponse` response data
- Increment: `current_usage += creditsUsed`
- Nếu response không chứa `creditsUsed` (lỗi, field missing) → fallback increment +1 credit
- SQL: `INSERT ... ON CONFLICT (key_id, month) DO UPDATE SET current_usage = current_usage + $credits`
- Update in-memory UsageCache sau mỗi increment

### 3.2 Usage Cache (`usage/usage_cache.py`)

In-memory cache cho fast lookup khi routing.

```python
class UsageCache:
    _cache: dict[int, UsageEntry]  # key_id → {current_usage, usage_limit, is_active}
    _lock: asyncio.Lock

    async def load_from_db()           # Full load khi app start
    async def get(key_id) -> UsageEntry
    async def increment(key_id, amount)  # Update local cache
    async def refresh_limits(entries)    # Batch update từ sync worker
    def get_available_keys() -> list[int]  # Keys có remaining > 1%
```

- Load toàn bộ vào memory khi app startup (lifespan)
- Single async worker (`uvicorn --workers 1`) — 1 UsageCache duy nhất, không cần cross-process sync
- FastAPI + httpx là I/O-bound, 1 process async đủ xử lý hàng trăm concurrent requests

### 3.3 Fallback Router (`usage/fallback.py`)

**Pre-check** (trước khi gửi request):
- `remaining = (limit - current_usage) / limit`
- Nếu `remaining < 0.01` (dưới 1%) → `pick_fallback_key()`

**Post-check** (sau khi nhận 429 từ Kiro):
- Gọi `pick_fallback_key()` → retry request với key mới
- Nếu vẫn fail → trả 429 cho client

**`pick_fallback_key()`:**
- Query `usage_cache.get_available_keys()` — active keys có remaining > 1%
- Exclude current key
- Round-robin selection (atomic counter trong memory)
- Decrypt `key_encrypted` → return key + update auth header
- Nếu không còn key nào → raise `NoAvailableKeyError`

### 3.4 Sync Worker (`usage/sync_worker.py`)

2 periodic asyncio tasks:

**Task 1 — Sync Usage Limits (mỗi 10 phút):**
- For each active key: call `getUsageLimits` API
- Update `key_usage.usage_limit` và `key_usage.current_usage` từ response
- Update `kiro_user_id` mapping nếu có
- Refresh `UsageCache`

Single async worker nên không cần leader election — sync tasks chạy trực tiếp trong process.

### 3.5 Scheduler (`usage/scheduler.py`)

Lifespan integration:
- Startup: start sync worker tasks (asyncio.create_task)
- Shutdown: cancel tasks, flush pending increments

---

## 4. Dashboard API

Tất cả routes mount dưới prefix `/api/`, tách biệt khỏi proxy routes (`/v1/`).

### 4.1 Authentication

```
POST /api/auth/login      → { access_token (15min), refresh_token (7d) }
POST /api/auth/refresh    → { access_token, refresh_token }
```

JWT payload: `{ sub: user_id, role: "admin"|"user", exp }`.
Dependencies: `get_current_user` (decode JWT), `require_admin` (check role).

### 4.2 User Management (admin only)

```
GET    /api/users          # list users
POST   /api/users          # create user
GET    /api/users/{id}     # user detail + mapped keys
PUT    /api/users/{id}     # update (deactivate, reset password)
```

### 4.3 API Key Management

```
GET    /api/keys           # list (admin: all, user: own keys)
POST   /api/keys           # register key (masked on response)
PUT    /api/keys/{id}      # toggle active/inactive
DELETE /api/keys/{id}      # soft delete (set inactive)
GET    /api/keys/{id}/usage  # usage history
```

Response luôn mask key: `{ key_prefix, key_suffix }` — không bao giờ trả full key.

### 4.4 Overview / KPIs

```
GET /api/overview → {
    total_credits_used,    # tháng hiện tại
    total_credits_limit,   # tổng limit tất cả keys
    active_users,
    active_keys,
    daily_usage: [{date, credits}]  # 30 ngày gần nhất
}
```

### 4.5 System Config (admin only)

```
GET /api/config
PUT /api/config → {
    enable_model_override: bool,
    enforced_global_model: str,
    enable_usage_sharing: bool
}
```

Update → ghi DB `system_config` → invalidate in-memory config cache.

### 4.6 User Import (admin only)

```
POST /api/import/users
  Content-Type: multipart/form-data
  File: CSV hoặc JSON [kiro_user_id, email, username]
  → upsert vào kiro_user_mappings
  → return { imported, updated, errors }
```

---

## 5. Integration với Existing Proxy

### 5.1 App Lifespan (`main.py` mở rộng)

**Startup:**
1. Init DB engine + check migrations
2. Load SystemConfig từ DB → in-memory config cache
3. Load UsageCache từ DB (active keys + current month)
4. Start sync worker tasks (asyncio.create_task)
5. Mount dashboard router (`/api/`)
6. Existing init (httpx, auth manager, model cache) — giữ nguyên

**Shutdown:**
1. Cancel sync worker tasks
2. Flush pending usage increments
3. Close DB engine
4. Existing cleanup — giữ nguyên

### 5.2 Proxy Touch Points (chỉ 2 files sửa)

**`api_key_mode.py`:**
- `handle_chat_openai()` / `handle_chat_anthropic()`:
  - TRƯỚC request: `fallback.pre_check(key_hash)` — swap key nếu cạn
  - SAU response stream: `BackgroundTask → tracker.increment(key_id, credits_used)`
  - Extract `creditsUsed` từ response; fallback +1 nếu không có

**`http_client.py`:**
- Bắt 429 response → nếu `enable_usage_sharing`: gọi `fallback.post_check()` → retry 1 lần

### 5.3 Config Flow

```
ENV vars (static):     DATABASE_URL, ENCRYPTION_KEY, JWT_SECRET, JWT_EXPIRY
DB system_config:      enable_model_override, enforced_global_model, enable_usage_sharing
In-memory ConfigCache: load từ DB startup, invalidate khi admin PUT /api/config
```

### 5.4 Backward Compatibility

- Nếu `DATABASE_URL` không set → skip toàn bộ DB init, dashboard, usage engine
- Proxy hoạt động 100% như cũ (stateless mode)
- Opt-in feature — chỉ kích hoạt khi có DB config

---

## 6. New Dependencies

```
sqlalchemy[asyncio]    # ORM + async support
asyncpg                # PostgreSQL async driver
alembic                # Database migrations
python-jose[cryptography]  # JWT encode/decode
passlib[bcrypt]        # Password hashing
cryptography           # Fernet encryption cho API keys
python-multipart       # File upload (CSV import)
```

---

## 7. ENV Configuration (new)

```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/kiro_gateway
ENCRYPTION_KEY=<fernet-key>       # Fernet.generate_key()
JWT_SECRET=<random-secret>
JWT_ACCESS_EXPIRY=900             # 15 minutes
JWT_REFRESH_EXPIRY=604800         # 7 days
ADMIN_USERNAME=admin              # initial admin account (first run)
ADMIN_PASSWORD=<initial-password>
```
