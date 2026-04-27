# Analytics Redesign — 4 Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the `/analytics` page into a fully data-driven 4-module dashboard backed by a new `daily_usage` table and `GET /api/overview/analytics` endpoint.

**Architecture:** New `daily_usage` table stores per-key per-day credits; an in-memory buffer (`DailyBuffer`) batches writes and flushes every 60s with graceful-shutdown drain. A new analytics endpoint aggregates daily series + user totals for the selected time window (7d/30d/90d). The frontend page is rebuilt with 4 glass-panel modules using Recharts.

**Tech Stack:** Python / FastAPI / SQLAlchemy async / Alembic / Recharts / React Query / Next.js App Router / Playwright

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `alembic/versions/xxxx_add_daily_usage.py` | Create | Migration: add `daily_usage` table |
| `kiro/db/models.py` | Modify | Add `DailyUsage` ORM model |
| `kiro/db/repositories.py` | Modify | Add `increment_daily_usage()` |
| `kiro/usage/daily_buffer.py` | Create | In-memory buffer + 60s flush + graceful shutdown |
| `kiro/usage/tracker.py` | Modify | Call `daily_buffer.record()` after existing `track_usage` |
| `kiro/usage/scheduler.py` | Modify | Start/stop daily buffer task in `startup()`/`shutdown()` |
| `kiro/dashboard/schemas.py` | Modify | Add `DailySeries`, `UserCredit`, `TopUser`, `CreditShare`, `AnalyticsResponse` |
| `kiro/dashboard/routes_analytics.py` | Create | `GET /overview/analytics?range=7d\|30d\|90d` |
| `kiro/dashboard/__init__.py` | Modify | Register analytics router |
| `tests/unit/test_daily_buffer.py` | Create | Buffer unit tests |
| `tests/unit/test_routes_analytics.py` | Create | Endpoint unit tests |
| `webui/lib/types.ts` | Modify | Add analytics types |
| `webui/hooks/use-analytics.ts` | Create | `useAnalytics(range)` hook |
| `webui/components/charts/bar-chart-credits.tsx` | Create | Bar chart: username → credits |
| `webui/components/charts/donut-chart-share.tsx` | Create | Donut chart: credit share |
| `webui/app/(dashboard)/analytics/page.tsx` | Modify | Full rewrite: 4-module layout |
| `webui/tests/e2e/credits-usage.spec.ts` | Modify | Add 4-module assertions |

---

## Task 1: Add `daily_usage` table — migration + ORM model

**Files:**
- Modify: `kiro/db/models.py`
- Create: `alembic/versions/<hash>_add_daily_usage.py`

- [ ] **Step 1: Add `DailyUsage` ORM model to `kiro/db/models.py`**

Add after the `KeyUsage` class (after line ~60):

```python
class DailyUsage(Base):
    __tablename__ = "daily_usage"
    __table_args__ = (
        UniqueConstraint("key_id", "date", name="uq_daily_usage_key_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_id: Mapped[int] = mapped_column(Integer, ForeignKey("api_keys.id"), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # "YYYY-MM-DD"
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
```

The existing import line already has `UniqueConstraint` — no change needed:
```python
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
```

- [ ] **Step 2: Generate the Alembic migration**

```bash
alembic revision --autogenerate -m "add_daily_usage"
```

Expected: new file created in `alembic/versions/`.

- [ ] **Step 3: Verify the generated migration**

Open the generated file and confirm `upgrade()` contains a `create_table('daily_usage', ...)` block with columns `id`, `key_id`, `date`, `credits`, `created_at` and the unique constraint `uq_daily_usage_key_date`. Confirm `downgrade()` has `op.drop_table('daily_usage')`.

- [ ] **Step 4: Apply the migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade 2fd297472749 -> <new_hash>, add_daily_usage`

- [ ] **Step 5: Commit**

```bash
git add kiro/db/models.py alembic/versions/
git commit -m "feat: add daily_usage table for per-day credit tracking"
```

---

## Task 2: Add `increment_daily_usage` repository function

**Files:**
- Modify: `kiro/db/repositories.py`
- Test: `tests/unit/test_repositories.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_repositories.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from kiro.db.repositories import increment_daily_usage


@pytest.mark.asyncio
async def test_increment_daily_usage_calls_execute():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    await increment_daily_usage(session, key_id=1, date="2026-04-27", amount=42)
    session.execute.assert_called_once()
    session.commit.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_repositories.py::test_increment_daily_usage_calls_execute -v
```

Expected: `FAILED` — `ImportError: cannot import name 'increment_daily_usage'`

- [ ] **Step 3: Implement `increment_daily_usage` in `kiro/db/repositories.py`**

Add after the `get_all_usage_for_month` function:

```python
async def increment_daily_usage(session: AsyncSession, key_id: int, date: str, amount: int = 1) -> None:
    from kiro.db.models import DailyUsage
    stmt = pg_insert(DailyUsage).values(key_id=key_id, date=date, credits=amount)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_daily_usage_key_date",
        set_={"credits": DailyUsage.credits + amount},
    )
    await session.execute(stmt)
    await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_repositories.py::test_increment_daily_usage_calls_execute -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add kiro/db/repositories.py tests/unit/test_repositories.py
git commit -m "feat: add increment_daily_usage repository function"
```

---

## Task 3: Build `DailyBuffer` — in-memory buffer with 60s flush + graceful shutdown

**Files:**
- Create: `kiro/usage/daily_buffer.py`
- Create: `tests/unit/test_daily_buffer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_daily_buffer.py`:

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from kiro.usage.daily_buffer import DailyBuffer


@pytest.mark.asyncio
async def test_record_accumulates():
    buf = DailyBuffer()
    buf.record(1, "2026-04-27", 10)
    buf.record(1, "2026-04-27", 5)
    buf.record(2, "2026-04-27", 20)
    assert buf._buffer[(1, "2026-04-27")] == 15
    assert buf._buffer[(2, "2026-04-27")] == 20


@pytest.mark.asyncio
async def test_flush_clears_buffer():
    buf = DailyBuffer()
    buf.record(1, "2026-04-27", 10)

    with patch("kiro.usage.daily_buffer.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("kiro.usage.daily_buffer.increment_daily_usage", new_callable=AsyncMock):
            await buf.flush()

    assert len(buf._buffer) == 0


@pytest.mark.asyncio
async def test_flush_empty_buffer_is_noop():
    buf = DailyBuffer()
    with patch("kiro.usage.daily_buffer.async_session_factory") as mock_factory:
        await buf.flush()
    mock_factory.assert_not_called()


@pytest.mark.asyncio
async def test_graceful_shutdown_drains():
    buf = DailyBuffer()
    buf.record(1, "2026-04-27", 99)
    flushed = []

    async def fake_flush():
        flushed.append(dict(buf._buffer))
        buf._buffer.clear()

    buf.flush = fake_flush
    await buf.stop()
    assert len(flushed) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_daily_buffer.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'kiro.usage.daily_buffer'`

- [ ] **Step 3: Implement `kiro/usage/daily_buffer.py`**

```python
import asyncio
from collections import defaultdict
from datetime import date

from loguru import logger

from kiro.db.engine import async_session_factory
from kiro.db.repositories import increment_daily_usage

_FLUSH_INTERVAL = 60


class DailyBuffer:
    def __init__(self) -> None:
        self._buffer: dict[tuple[int, str], int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    def record(self, key_id: int, date_str: str, amount: int) -> None:
        self._buffer[(key_id, date_str)] += amount

    async def flush(self) -> None:
        if not self._buffer:
            return
        async with self._lock:
            snapshot = dict(self._buffer)
            self._buffer.clear()
        if not snapshot:
            return
        try:
            async with async_session_factory() as session:
                for (key_id, date_str), credits in snapshot.items():
                    await increment_daily_usage(session, key_id, date_str, credits)
            logger.debug(f"DailyBuffer: flushed {len(snapshot)} entries")
        except Exception as e:
            logger.error(f"DailyBuffer: flush failed: {e}")
            async with self._lock:
                for k, v in snapshot.items():
                    self._buffer[k] += v

    async def _run_loop(self) -> None:
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL)
            await self.flush()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())
        logger.info("DailyBuffer: flush task started")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.flush()
        logger.info("DailyBuffer: flushed and stopped")


daily_buffer = DailyBuffer()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_daily_buffer.py -v
```

Expected: all 4 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add kiro/usage/daily_buffer.py tests/unit/test_daily_buffer.py
git commit -m "feat: add DailyBuffer in-memory credit buffer with graceful shutdown"
```

---

## Task 4: Wire `DailyBuffer` into tracker and scheduler

**Files:**
- Modify: `kiro/usage/tracker.py`
- Modify: `kiro/usage/scheduler.py`

- [ ] **Step 1: Call `daily_buffer.record()` in `track_usage`**

In `kiro/usage/tracker.py`, add the import at the top:

```python
from kiro.usage.daily_buffer import daily_buffer
```

Then in `track_usage`, after the `await usage_cache.increment(key_id, amount)` line, add:

```python
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_buffer.record(key_id, today, amount)
```

Full updated function:

```python
async def track_usage(key_id: int, credits_used: int | None = None) -> None:
    amount = credits_used if credits_used is not None and credits_used > 0 else 1
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        if async_session_factory is None:
            return
        async with async_session_factory() as session:
            await increment_usage(session, key_id, month, amount)
        await usage_cache.increment(key_id, amount)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_buffer.record(key_id, today, amount)
        logger.debug(f"Tracked {amount} credits for key_id={key_id} month={month}")
    except Exception as e:
        logger.error(f"Failed to track usage for key_id={key_id}: {e}")
```

- [ ] **Step 2: Start/stop `DailyBuffer` in scheduler**

In `kiro/usage/scheduler.py`, add the import:

```python
from kiro.usage.daily_buffer import daily_buffer
```

In `startup()`, after `_sync_task = asyncio.create_task(run_sync_loop())`, add:

```python
    daily_buffer.start()
    logger.info("Usage management: daily buffer started")
```

In `shutdown()`, after cancelling `_sync_task`, add:

```python
    await daily_buffer.stop()
    logger.info("Usage management: daily buffer stopped")
```

- [ ] **Step 3: Run existing tests to confirm nothing broke**

```bash
pytest tests/unit/test_usage_tracker.py tests/unit/test_daily_buffer.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 4: Commit**

```bash
git add kiro/usage/tracker.py kiro/usage/scheduler.py
git commit -m "feat: wire DailyBuffer into usage tracker and scheduler lifecycle"
```

---

## Task 5: Add analytics schemas to `kiro/dashboard/schemas.py`

**Files:**
- Modify: `kiro/dashboard/schemas.py`

- [ ] **Step 1: Add the new schema classes**

Append to the end of `kiro/dashboard/schemas.py`:

```python
# --- Analytics ---

class DailySeries(BaseModel):
    date: str
    credits: int


class UserCredit(BaseModel):
    user_id: int
    username: str
    credits: int


class TopUser(BaseModel):
    rank: int
    user_id: int
    username: str
    credits: int
    share_pct: float


class CreditShare(BaseModel):
    user_id: int
    username: str
    credits: int
    pct: float


class AnalyticsResponse(BaseModel):
    range: str
    daily_series: list[DailySeries]
    user_credits: list[UserCredit]
    top_users: list[TopUser]
    credit_share: list[CreditShare]
```

- [ ] **Step 2: Run existing schema tests to confirm nothing broke**

```bash
pytest tests/unit/test_dashboard_schemas.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 3: Commit**

```bash
git add kiro/dashboard/schemas.py
git commit -m "feat: add analytics response schemas"
```

---

## Task 6: Implement `GET /overview/analytics` endpoint

**Files:**
- Create: `kiro/dashboard/routes_analytics.py`
- Create: `tests/unit/test_routes_analytics.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_routes_analytics.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient
from fastapi import FastAPI
from kiro.dashboard.routes_analytics import router
from kiro.dashboard.deps import get_current_user
from kiro.db.engine import get_session

app = FastAPI()
app.include_router(router)  # router already has prefix="/overview"

fake_user = MagicMock(id=1, username="admin", role="admin")

app.dependency_overrides[get_current_user] = lambda: fake_user
app.dependency_overrides[get_session] = lambda: AsyncMock()


@pytest.mark.asyncio
async def test_analytics_returns_all_fields():
    with patch("kiro.dashboard.routes_analytics._aggregate_analytics", new_callable=AsyncMock) as mock_agg:
        from kiro.dashboard.schemas import AnalyticsResponse
        mock_agg.return_value = AnalyticsResponse(
            range="7d",
            daily_series=[],
            user_credits=[],
            top_users=[],
            credit_share=[],
        )
        async with AsyncClient(app=app, base_url="http://test") as client:
            resp = await client.get("/overview/analytics?range=7d")
        assert resp.status_code == 200
        data = resp.json()
        assert data["range"] == "7d"
        assert "daily_series" in data
        assert "user_credits" in data
        assert "top_users" in data
        assert "credit_share" in data


@pytest.mark.asyncio
async def test_analytics_invalid_range_returns_422():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/overview/analytics?range=999d")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analytics_default_range_is_7d():
    with patch("kiro.dashboard.routes_analytics._aggregate_analytics", new_callable=AsyncMock) as mock_agg:
        from kiro.dashboard.schemas import AnalyticsResponse
        mock_agg.return_value = AnalyticsResponse(
            range="7d", daily_series=[], user_credits=[], top_users=[], credit_share=[]
        )
        async with AsyncClient(app=app, base_url="http://test") as client:
            resp = await client.get("/overview/analytics")
        assert resp.status_code == 200
        mock_agg.assert_called_once()
        call_kwargs = mock_agg.call_args
        assert call_kwargs.kwargs.get("range_key") == "7d" or call_kwargs.args[1] == "7d"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_routes_analytics.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'kiro.dashboard.routes_analytics'`

- [ ] **Step 3: Implement `kiro/dashboard/routes_analytics.py`**

```python
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user
from kiro.dashboard.schemas import (
    AnalyticsResponse, CreditShare, DailySeries, TopUser, UserCredit,
)
from kiro.db.engine import get_session
from kiro.db.models import ApiKey, DailyUsage, User

router = APIRouter(prefix="/overview", tags=["analytics"])

_RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90}


async def _aggregate_analytics(
    session: AsyncSession, range_key: str
) -> AnalyticsResponse:
    days = _RANGE_DAYS[range_key]
    today = date.today()
    start = today - timedelta(days=days - 1)
    start_str = start.isoformat()
    end_str = today.isoformat()

    # Daily series: sum credits per date across all keys
    daily_rows = (await session.execute(
        select(DailyUsage.date, func.sum(DailyUsage.credits).label("credits"))
        .where(DailyUsage.date >= start_str, DailyUsage.date <= end_str)
        .group_by(DailyUsage.date)
        .order_by(DailyUsage.date)
    )).all()

    daily_map = {row.date: row.credits for row in daily_rows}
    daily_series = [
        DailySeries(
            date=(start + timedelta(days=i)).isoformat(),
            credits=daily_map.get((start + timedelta(days=i)).isoformat(), 0),
        )
        for i in range(days)
    ]

    # Per-user credits: join daily_usage -> api_keys -> users
    user_rows = (await session.execute(
        select(User.id, User.username, func.sum(DailyUsage.credits).label("credits"))
        .join(ApiKey, ApiKey.user_id == User.id)
        .join(DailyUsage, DailyUsage.key_id == ApiKey.id)
        .where(DailyUsage.date >= start_str, DailyUsage.date <= end_str)
        .group_by(User.id, User.username)
        .order_by(func.sum(DailyUsage.credits).desc())
    )).all()

    total = sum(r.credits for r in user_rows) or 1

    user_credits = [
        UserCredit(user_id=r.id, username=r.username, credits=r.credits)
        for r in user_rows
    ]
    top_users = [
        TopUser(
            rank=i + 1,
            user_id=r.id,
            username=r.username,
            credits=r.credits,
            share_pct=round(r.credits / total * 100, 1),
        )
        for i, r in enumerate(user_rows[:10])
    ]
    credit_share = [
        CreditShare(
            user_id=r.id,
            username=r.username,
            credits=r.credits,
            pct=round(r.credits / total * 100, 1),
        )
        for r in user_rows
    ]

    return AnalyticsResponse(
        range=range_key,
        daily_series=daily_series,
        user_credits=user_credits,
        top_users=top_users,
        credit_share=credit_share,
    )


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    range: str = Query(default="7d", pattern="^(7d|30d|90d)$"),
    caller: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsResponse:
    return await _aggregate_analytics(session, range)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_routes_analytics.py -v
```

Expected: all 3 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add kiro/dashboard/routes_analytics.py tests/unit/test_routes_analytics.py
git commit -m "feat: add GET /overview/analytics endpoint with 7d/30d/90d aggregation"
```

---

## Task 7: Register analytics router in dashboard

**Files:**
- Modify: `kiro/dashboard/__init__.py`

- [ ] **Step 1: Import and register the analytics router**

In `kiro/dashboard/__init__.py`, add the import:

```python
from kiro.dashboard.routes_analytics import router as analytics_router
```

Then add the include line after the existing routers:

```python
dashboard_router.include_router(analytics_router)
```

Full file after change:

```python
from fastapi import APIRouter

from kiro.dashboard.routes_auth import router as auth_router
from kiro.dashboard.routes_users import router as users_router
from kiro.dashboard.routes_keys import router as keys_router
from kiro.dashboard.routes_overview import router as overview_router
from kiro.dashboard.routes_config import router as config_router
from kiro.dashboard.routes_import import router as import_router
from kiro.dashboard.routes_analytics import router as analytics_router

dashboard_router = APIRouter(prefix="/api", tags=["dashboard"])
dashboard_router.include_router(auth_router)
dashboard_router.include_router(users_router)
dashboard_router.include_router(keys_router)
dashboard_router.include_router(overview_router)
dashboard_router.include_router(config_router)
dashboard_router.include_router(import_router)
dashboard_router.include_router(analytics_router)
```

- [ ] **Step 2: Run all backend tests to confirm nothing broke**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: all tests `PASSED`

- [ ] **Step 3: Commit**

```bash
git add kiro/dashboard/__init__.py
git commit -m "feat: register analytics router in dashboard"
```

---

## Task 8: Add analytics types to frontend

**Files:**
- Modify: `webui/lib/types.ts`

- [ ] **Step 1: Append analytics types to `webui/lib/types.ts`**

```typescript
// --- Analytics ---

export interface DailySeries {
  date: string;
  credits: number;
}

export interface UserCredit {
  user_id: number;
  username: string;
  credits: number;
}

export interface TopUser {
  rank: number;
  user_id: number;
  username: string;
  credits: number;
  share_pct: number;
}

export interface CreditShare {
  user_id: number;
  username: string;
  credits: number;
  pct: number;
}

export interface AnalyticsResponse {
  range: string;
  daily_series: DailySeries[];
  user_credits: UserCredit[];
  top_users: TopUser[];
  credit_share: CreditShare[];
}
```

- [ ] **Step 2: Commit**

```bash
git add webui/lib/types.ts
git commit -m "feat: add analytics TypeScript types"
```

---

## Task 9: Create `useAnalytics` hook

**Files:**
- Create: `webui/hooks/use-analytics.ts`

- [ ] **Step 1: Create `webui/hooks/use-analytics.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { AnalyticsResponse } from "@/lib/types";

export type AnalyticsRange = "7d" | "30d" | "90d";

export function useAnalytics(range: AnalyticsRange = "7d") {
  return useQuery({
    queryKey: ["analytics", range],
    queryFn: async () => {
      const res = await apiClient.get<AnalyticsResponse>(`/overview/analytics?range=${range}`);
      return res.data;
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add webui/hooks/use-analytics.ts
git commit -m "feat: add useAnalytics hook"
```

---

## Task 10: Create `BarChartCredits` component

**Files:**
- Create: `webui/components/charts/bar-chart-credits.tsx`

- [ ] **Step 1: Create `webui/components/charts/bar-chart-credits.tsx`**

```tsx
"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { UserCredit } from "@/lib/types";
import { formatCredits } from "@/lib/utils";

interface Props {
  data: UserCredit[];
}

export function BarChartCredits({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-on-surface-variant text-sm">
        No data for this period.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e4e1ee" vertical={false} />
        <XAxis
          dataKey="username"
          tick={{ fontSize: 12, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 12, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => formatCredits(v)}
        />
        <Tooltip
          contentStyle={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.9)",
            borderRadius: "12px",
            boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
          }}
          formatter={(value) => [formatCredits(Number(value ?? 0)), "Credits"]}
        />
        <Bar dataKey="credits" fill="#6366f1" radius={[6, 6, 0, 0]} barSize={40} />
      </BarChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add webui/components/charts/bar-chart-credits.tsx
git commit -m "feat: add BarChartCredits component"
```

---

## Task 11: Create `DonutChartShare` component

**Files:**
- Create: `webui/components/charts/donut-chart-share.tsx`

- [ ] **Step 1: Create `webui/components/charts/donut-chart-share.tsx`**

```tsx
"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { CreditShare } from "@/lib/types";
import { formatCredits } from "@/lib/utils";

const COLORS = [
  "#6366f1", "#0ea5e9", "#8b5cf6", "#10b981", "#f59e0b",
  "#ef4444", "#ec4899", "#14b8a6", "#f97316", "#84cc16",
];

interface Props {
  data: CreditShare[];
}

export function DonutChartShare({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-on-surface-variant text-sm">
        No data for this period.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie
          data={data}
          dataKey="credits"
          nameKey="username"
          cx="50%"
          cy="45%"
          innerRadius="50%"
          outerRadius="70%"
          paddingAngle={2}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.9)",
            borderRadius: "12px",
            boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
          }}
          formatter={(value, name, props) => [
            `${formatCredits(Number(value))} (${props.payload.pct}%)`,
            name,
          ]}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          formatter={(value) => (
            <span style={{ fontSize: 12, color: "#464555" }}>{value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add webui/components/charts/donut-chart-share.tsx
git commit -m "feat: add DonutChartShare component"
```

---

## Task 12: Rewrite analytics page with 4-module layout

**Files:**
- Modify: `webui/app/(dashboard)/analytics/page.tsx`

- [ ] **Step 1: Rewrite `webui/app/(dashboard)/analytics/page.tsx`**

```tsx
"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalytics, type AnalyticsRange } from "@/hooks/use-analytics";
import { BarChartCredits } from "@/components/charts/bar-chart-credits";
import { AreaChartUsage } from "@/components/charts/area-chart-usage";
import { DonutChartShare } from "@/components/charts/donut-chart-share";
import { formatCredits } from "@/lib/utils";

const RANGES: AnalyticsRange[] = ["7d", "30d", "90d"];

export default function AnalyticsPage() {
  const [range, setRange] = useState<AnalyticsRange>("7d");
  const { data, isLoading, isError } = useAnalytics(range);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-h1 font-bold text-on-surface tracking-tight">Usage Analytics</h1>
          <p className="text-on-surface-variant mt-1 text-sm">Detailed breakdown of credit consumption.</p>
        </div>
        <div className="glass-panel flex items-center rounded-lg p-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                range === r
                  ? "bg-white shadow-sm text-primary border border-outline-variant"
                  : "text-on-surface-variant hover:text-primary"
              }`}
            >
              {r.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Row 1: Bar + Area */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel rounded-3xl p-6">
          <h3 className="text-base font-semibold text-on-surface mb-4">User Credit Consumption</h3>
          <div className="h-[280px]">
            {isLoading ? (
              <Skeleton className="h-full w-full rounded-xl" />
            ) : isError ? (
              <ErrorState />
            ) : (
              <BarChartCredits data={data?.user_credits ?? []} />
            )}
          </div>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <h3 className="text-base font-semibold text-on-surface mb-4">Daily Credit Consumption</h3>
          <div className="h-[280px]">
            {isLoading ? (
              <Skeleton className="h-full w-full rounded-xl" />
            ) : isError ? (
              <ErrorState />
            ) : (
              <AreaChartUsage data={data?.daily_series ?? []} />
            )}
          </div>
        </div>
      </div>

      {/* Row 2: Top Users + Donut */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel rounded-3xl p-0 overflow-hidden">
          <div className="px-6 py-4 border-b border-outline-variant/30">
            <h3 className="text-base font-semibold text-on-surface">Top Users</h3>
          </div>
          <div className="p-2">
            {isLoading ? (
              <div className="p-4 space-y-3">
                {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
              </div>
            ) : isError ? (
              <div className="p-6"><ErrorState /></div>
            ) : !data?.top_users.length ? (
              <EmptyState />
            ) : (
              data.top_users.map((u) => (
                <div key={u.user_id} className="flex items-center justify-between p-3 rounded-xl hover:bg-surface-container transition-colors">
                  <div className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded-full bg-primary-container flex items-center justify-center text-[10px] font-bold text-on-primary-container">
                      {u.rank}
                    </span>
                    <span className="text-sm font-medium text-on-surface">{u.username}</span>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-primary">{formatCredits(u.credits)}</div>
                    <div className="text-[10px] text-on-surface-variant">{u.share_pct}%</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <h3 className="text-base font-semibold text-on-surface mb-4">Credit Consume By Users</h3>
          <div className="h-[280px]">
            {isLoading ? (
              <Skeleton className="h-full w-full rounded-xl" />
            ) : isError ? (
              <ErrorState />
            ) : (
              <DonutChartShare data={data?.credit_share ?? []} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex items-center justify-center h-20 text-on-surface-variant text-sm">
      No data for this period.
    </div>
  );
}

function ErrorState() {
  return (
    <div className="flex items-center justify-center h-full text-error text-sm">
      Failed to load. Please refresh.
    </div>
  );
}
```

- [ ] **Step 2: Verify `formatCredits` exists in `webui/lib/utils.ts`**

```bash
grep -n "formatCredits" webui/lib/utils.ts
```

If it doesn't exist, add it:

```typescript
export function formatCredits(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}
```

- [ ] **Step 3: Commit**

```bash
git add webui/app/(dashboard)/analytics/page.tsx webui/lib/utils.ts
git commit -m "feat: rewrite analytics page with 4-module layout"
```

---

## Task 13: Update Playwright e2e tests for analytics page

**Files:**
- Modify: `webui/tests/e2e/credits-usage.spec.ts`

- [ ] **Step 1: Add 4-module assertions to `webui/tests/e2e/credits-usage.spec.ts`**

Replace the existing `"analytics page should show credit consumption data"` test and add new tests:

```typescript
  test("analytics page should show all 4 modules", async ({ page }) => {
    await page.goto("/analytics");
    const main = page.locator("main");

    await expect(main.getByText("User Credit Consumption")).toBeVisible({ timeout: 10000 });
    await expect(main.getByText("Daily Credit Consumption")).toBeVisible();
    await expect(main.getByText("Top Users")).toBeVisible();
    await expect(main.getByText("Credit Consume By Users")).toBeVisible();
  });

  test("analytics timeframe toggle switches range", async ({ page }) => {
    await page.goto("/analytics");
    const main = page.locator("main");

    await expect(main.getByText("User Credit Consumption")).toBeVisible({ timeout: 10000 });

    // Default is 7D active
    const btn7d = main.getByRole("button", { name: "7D" });
    const btn30d = main.getByRole("button", { name: "30D" });
    const btn90d = main.getByRole("button", { name: "90D" });

    await expect(btn7d).toBeVisible();
    await expect(btn30d).toBeVisible();
    await expect(btn90d).toBeVisible();

    // Click 30D — page should still show all 4 modules
    await btn30d.click();
    await expect(main.getByText("User Credit Consumption")).toBeVisible();
    await expect(main.getByText("Daily Credit Consumption")).toBeVisible();

    // Click 90D
    await btn90d.click();
    await expect(main.getByText("Top Users")).toBeVisible();
  });
```

- [ ] **Step 2: Run the e2e tests**

```bash
cd webui && npx playwright test credits-usage.spec.ts --reporter=list
```

Expected: all tests pass (the new analytics tests may show empty state if no data, but panels must be visible).

- [ ] **Step 3: Commit**

```bash
git add webui/tests/e2e/credits-usage.spec.ts
git commit -m "test: add e2e assertions for 4-module analytics page"
```

---

## Task 14: Full regression check

- [ ] **Step 1: Run all backend unit tests**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: all tests `PASSED`

- [ ] **Step 2: Run all e2e tests**

```bash
cd webui && npx playwright test --reporter=list
```

Expected: all tests pass

- [ ] **Step 3: Final commit if any loose files**

```bash
git status
```

If any modified files remain unstaged, stage and commit them:

```bash
git add <files>
git commit -m "chore: finalize analytics redesign"
```

