# Analytics Redesign — 4 Modules

**Date:** 2026-04-27  
**Status:** Approved

## Overview

Redesign the `/analytics` page from a single placeholder chart into a fully data-driven 4-module dashboard. Applies the glass-panel visual style from `references/usage-management/design/analyst.html`. Data is real end-to-end via a new backend endpoint and a new `daily_usage` table.

---

## Phase 1 — Database & Data Collection

### New table: `daily_usage`

```sql
CREATE TABLE daily_usage (
    id         SERIAL PRIMARY KEY,
    key_id     INTEGER NOT NULL REFERENCES api_keys(id),
    date       DATE NOT NULL,
    credits    INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (key_id, date)
);
```

Alembic migration added alongside existing migrations.

### In-memory buffer: `kiro/usage/daily_buffer.py`

- `defaultdict(int)` keyed by `(key_id: int, date: str)`, protected by `asyncio.Lock`
- `record(key_id, date, amount)` — increments in-memory only, no DB I/O, no await
- `flush()` — snapshots dict, clears it, creates its own DB session via `AsyncSessionLocal` from the engine, batch-upserts via `ON CONFLICT (key_id, date) DO UPDATE SET credits = credits + excluded.credits`, then closes the session
- Background asyncio task flushes every 60 seconds
- **Graceful shutdown**: FastAPI lifespan cancels the background task, then calls one final `flush()` to drain remaining credits before process exits

### Gateway integration

The existing credit-recording path in `routes_openai.py` / `routes_anthropic.py` already extracts `creditsUsed` from Kiro's `getAssistanceResponse` and calls `increment_usage()`. Extend that same call site to also call `daily_buffer.record(key_id, today_str, credits_used)` — synchronous, no await, no DB round-trip per request.

---

## Phase 2 — Backend API

### New endpoint

```
GET /api/overview/analytics?range=7d|30d|90d
```

- Auth: `get_current_user` dependency (same as `routes_overview.py`), no role restriction
- New file: `kiro/dashboard/routes_analytics.py`
- Registered in `kiro/dashboard/__init__.py`

### Response schema

```python
class DailySeries(BaseModel):
    date: str       # "YYYY-MM-DD"
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
    daily_series: list[DailySeries]    # zero-filled for missing dates
    user_credits: list[UserCredit]     # all users, sorted desc by credits
    top_users: list[TopUser]           # top 10, with rank and share_pct
    credit_share: list[CreditShare]    # same data, donut-ready
```

### Aggregation logic

1. Compute `start_date = today - N days` (7, 30, or 90)
2. Join `daily_usage → api_keys → users`, filter `date >= start_date`
3. `daily_series`: group by date, sum credits; zero-fill missing dates in Python by generating the full date range and merging
4. `user_credits` / `top_users` / `credit_share`: group by user, sum credits, sort desc, compute `pct = user_credits / total * 100` (0 if total is 0)

---

## Phase 3 — Frontend

### New type (`lib/types.ts`)

```ts
interface DailySeries { date: string; credits: number; }
interface UserCredit { user_id: number; username: string; credits: number; }
interface TopUser { rank: number; user_id: number; username: string; credits: number; share_pct: number; }
interface CreditShare { user_id: number; username: string; credits: number; pct: number; }
interface AnalyticsResponse {
  range: string;
  daily_series: DailySeries[];
  user_credits: UserCredit[];
  top_users: TopUser[];
  credit_share: CreditShare[];
}
```

### New hook (`hooks/use-analytics.ts`)

`useAnalytics(range: "7d" | "30d" | "90d")` — calls `GET /api/overview/analytics?range=...`, `staleTime: 30_000`, `refetchInterval: 60_000`. Range state lives in the page component and is passed to the hook.

### Page layout (`app/(dashboard)/analytics/page.tsx`)

Replaces the current single-chart page entirely.

```
Header row:
  "Usage Analytics" title + subtitle
  Timeframe toggle: [7D | 30D | 90D]  (controls all 4 modules)

Row 1 — 2 equal columns:
  ┌─────────────────────────────┐  ┌─────────────────────────────┐
  │ User Credit Consumption     │  │ Daily Credit Consumption    │
  │ BarChart: username→credits  │  │ AreaChart: date→credits     │
  └─────────────────────────────┘  └─────────────────────────────┘

Row 2 — 2 equal columns:
  ┌─────────────────────────────┐  ┌─────────────────────────────┐
  │ Top Users                   │  │ Credit Consume By Users     │
  │ Ranked list: rank badge +   │  │ Donut chart: credit_share   │
  │ username + credits + share% │  │ with legend                 │
  └─────────────────────────────┘  └─────────────────────────────┘
```

### New chart components

- `components/charts/bar-chart-credits.tsx` — Recharts `BarChart`, `username` on X-axis, `credits` on Y-axis. Replaces `BarChartUsers` (which showed key count, not credits).
- `components/charts/donut-chart-share.tsx` — Recharts `PieChart` with `innerRadius`, renders `credit_share` data with a legend.

### States per module

Each of the 4 panels handles independently:
- **Loading**: `Skeleton` placeholder matching panel height
- **Empty**: "No data for this period" centered message
- **Error**: "Failed to load" with retry hint

All 4 share one hook call — no waterfall fetching.

---

## Phase 4 — Tests

### Backend

- Unit tests for `daily_buffer`: record accumulation, flush clears buffer, flush with empty buffer is a no-op, graceful shutdown drains
- Unit tests for `GET /overview/analytics`: empty DB returns zero-filled series, user aggregation sorts desc, tie-breaking is stable, multi-key users aggregate correctly, range parameter controls date window

### Frontend (Playwright)

Update `tests/e2e/credits-usage.spec.ts` (or add `analytics.spec.ts`) to assert:
- All 4 module panels are visible
- Timeframe toggle switches between 7D / 30D / 90D and re-fetches
- Empty state renders when no data

---

## Files Changed

| File | Action |
|------|--------|
| `alembic/versions/xxxx_add_daily_usage.py` | New migration |
| `kiro/db/models.py` | Add `DailyUsage` model |
| `kiro/db/repositories.py` | Add `increment_daily_usage()` |
| `kiro/usage/daily_buffer.py` | New — in-memory buffer + flush |
| `kiro/routes_openai.py` | Call `daily_buffer.record()` |
| `kiro/routes_anthropic.py` | Call `daily_buffer.record()` |
| `main.py` | Wire buffer start/stop into lifespan |
| `kiro/dashboard/schemas.py` | Add analytics schemas |
| `kiro/dashboard/routes_analytics.py` | New endpoint |
| `kiro/dashboard/__init__.py` | Register analytics router |
| `webui/lib/types.ts` | Add analytics types |
| `webui/hooks/use-analytics.ts` | New hook |
| `webui/app/(dashboard)/analytics/page.tsx` | Full rewrite |
| `webui/components/charts/bar-chart-credits.tsx` | New chart |
| `webui/components/charts/donut-chart-share.tsx` | New chart |
| `webui/tests/e2e/credits-usage.spec.ts` | Update/extend |
