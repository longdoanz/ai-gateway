from datetime import date, timedelta, timezone
from datetime import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aigw.dashboard.deps import require_admin
from aigw.dashboard.schemas import (
    AnalyticsResponse, TokenShare, DailySeries, TopUser, UserTokenUsage, UserDailySeries,
    GatewayKeyDailySeries, GatewayKeyUserUsage, GatewayKeyAnalyticsResponse,
)
from aigw.db.engine import get_session
from aigw.db.models import DailyUsage, GatewayKey, GatewayKeyDailyUsage, GatewayKeyUsage, User

router = APIRouter(prefix="/overview", tags=["analytics"])

_RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90}


async def _aggregate_analytics(
    session: AsyncSession, range_key: str
) -> AnalyticsResponse:
    days = _RANGE_DAYS[range_key]
    today = dt.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    start_str = start.isoformat()
    end_str = today.isoformat()

    # --- Overall daily series ---
    daily_rows = (await session.execute(
        select(
            DailyUsage.date,
            func.sum(DailyUsage.input_tokens).label("input_tokens"),
            func.sum(DailyUsage.output_tokens).label("output_tokens"),
        )
        .where(DailyUsage.date >= start_str, DailyUsage.date <= end_str)
        .group_by(DailyUsage.date)
        .order_by(DailyUsage.date)
    )).all()

    # NOTE: key_id IS NULL filter is currently dead code — _resolve_gateway_key always
    # resolves to a concrete API key_id, so GatewayKeyDailyUsage.key_id is never NULL.
    # System key usage is already captured in DailyUsage via _track_usage_background.
    # This block is kept as a safety net in case future code paths produce NULL key_id rows.
    gw_system_daily_rows = (await session.execute(
        select(
            GatewayKeyDailyUsage.date,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("input_tokens"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("output_tokens"),
        )
        .where(
            GatewayKeyDailyUsage.date >= start_str,
            GatewayKeyDailyUsage.date <= end_str,
            GatewayKeyDailyUsage.key_id.is_(None),
        )
        .group_by(GatewayKeyDailyUsage.date)
    )).all()
    gw_system_daily_map = {row.date: (row.input_tokens, row.output_tokens) for row in gw_system_daily_rows}

    daily_map: dict[str, tuple[int, int]] = {}
    for row in daily_rows:
        sys_in, sys_out = gw_system_daily_map.get(row.date, (0, 0))
        daily_map[row.date] = (row.input_tokens + sys_in, row.output_tokens + sys_out)
    for date_str, (sys_in, sys_out) in gw_system_daily_map.items():
        if date_str not in daily_map:
            daily_map[date_str] = (sys_in, sys_out)

    daily_series = [
        DailySeries(
            date=(start + timedelta(days=i)).isoformat(),
            input_tokens=daily_map.get((start + timedelta(days=i)).isoformat(), (0, 0))[0],
            output_tokens=daily_map.get((start + timedelta(days=i)).isoformat(), (0, 0))[1],
        )
        for i in range(days)
    ]

    # --- Per-user token totals (gateway keys) ---
    gw_user_token_rows = (await session.execute(
        select(
            User.username,
            User.email,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("input_tokens"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("output_tokens"),
        )
        .join(GatewayKey, GatewayKey.id == GatewayKeyDailyUsage.gateway_key_id)
        .join(User, User.id == GatewayKey.user_id)
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(User.username, User.email)
        .order_by(func.sum(GatewayKeyDailyUsage.input_tokens + GatewayKeyDailyUsage.output_tokens).desc())
    )).all()

    # --- Merge by email (primary key) or username ---
    # merged[merge_key] = {display_name, username, email, input_tokens, output_tokens}
    merged: dict[str, dict] = {}

    for r in gw_user_token_rows:
        email = r.email
        username = r.username
        key = (email.lower() if email else None) or (username.lower() if username else None)
        if not key:
            continue
        merged[key] = {
            "display_name": username or email or key,
            "username": username,
            "email": email,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
        }

    sorted_merged = sorted(merged.items(), key=lambda x: x[1]["input_tokens"] + x[1]["output_tokens"], reverse=True)
    total = sum(v["input_tokens"] + v["output_tokens"] for _, v in sorted_merged) or 1

    user_tokens = [
        UserTokenUsage(
            display_name=v["display_name"],
            username=v.get("username"),
            email=v.get("email"),
            input_tokens=v["input_tokens"],
            output_tokens=v["output_tokens"],
        )
        for _, v in sorted_merged
    ]
    top_users = [
        TopUser(
            rank=i + 1,
            display_name=v["display_name"],
            username=v.get("username"),
            email=v.get("email"),
            input_tokens=v["input_tokens"],
            output_tokens=v["output_tokens"],
            share_pct=round((v["input_tokens"] + v["output_tokens"]) / total * 100, 1),
        )
        for i, (_, v) in enumerate(sorted_merged[:10])
    ]
    token_share = [
        TokenShare(
            display_name=v["display_name"],
            username=v.get("username"),
            email=v.get("email"),
            input_tokens=v["input_tokens"],
            output_tokens=v["output_tokens"],
            pct=round((v["input_tokens"] + v["output_tokens"]) / total * 100, 1),
        )
        for _, v in sorted_merged
    ]

    # --- Per-user daily series (top 10) ---
    top_keys = [uid for uid, _ in sorted_merged[:10]]

    gw_daily_rows = (await session.execute(
        select(
            User.username,
            User.email,
            GatewayKeyDailyUsage.date,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("input_tokens"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("output_tokens"),
        )
        .join(GatewayKey, GatewayKey.id == GatewayKeyDailyUsage.gateway_key_id)
        .join(User, User.id == GatewayKey.user_id)
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(User.username, User.email, GatewayKeyDailyUsage.date)
    )).all()

    user_date_map: dict[str, dict[str, tuple[int, int]]] = {}

    for r in gw_daily_rows:
        email = r.email
        username = r.username
        key = (email.lower() if email else None) or (username.lower() if username else None)
        if not key or key not in top_keys:
            continue
        if key not in user_date_map:
            user_date_map[key] = {}
        prev_in, prev_out = user_date_map[key].get(r.date, (0, 0))
        user_date_map[key][r.date] = (prev_in + r.input_tokens, prev_out + r.output_tokens)

    user_daily_series = [
        UserDailySeries(
            display_name=merged[uid]["display_name"],
            username=merged[uid].get("username"),
            email=merged[uid].get("email"),
            daily=[
                DailySeries(
                    date=(start + timedelta(days=i)).isoformat(),
                    input_tokens=user_date_map.get(uid, {}).get((start + timedelta(days=i)).isoformat(), (0, 0))[0],
                    output_tokens=user_date_map.get(uid, {}).get((start + timedelta(days=i)).isoformat(), (0, 0))[1],
                )
                for i in range(days)
            ],
        )
        for uid in top_keys
        if uid in merged
    ]

    return AnalyticsResponse(
        time_range=range_key,
        daily_series=daily_series,
        user_tokens=user_tokens,
        top_users=top_users,
        token_share=token_share,
        user_daily_series=user_daily_series,
    )


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    range: str = Query(default="7d", pattern="^(7d|30d|90d)$"),
    caller: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsResponse:
    return await _aggregate_analytics(session, range)


@router.get("/analytics/gateway-key-usage", response_model=GatewayKeyAnalyticsResponse)
async def get_gateway_key_analytics(
    range_key: str = Query(default="7d", alias="range", pattern="^(7d|30d|90d)$"),
    caller: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> GatewayKeyAnalyticsResponse:
    days = _RANGE_DAYS[range_key]
    today = dt.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    start_str = start.isoformat()
    end_str = today.isoformat()

    daily_rows = (await session.execute(
        select(
            GatewayKeyDailyUsage.date,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("input_tokens"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("output_tokens"),
            func.sum(GatewayKeyDailyUsage.cache_read_tokens).label("cache_read_tokens"),
            func.sum(GatewayKeyDailyUsage.cache_creation_tokens).label("cache_creation_tokens"),
        )
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(GatewayKeyDailyUsage.date)
        .order_by(GatewayKeyDailyUsage.date)
    )).all()

    daily_map = {row.date: row for row in daily_rows}
    daily_series = []
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        row = daily_map.get(day)
        daily_series.append(GatewayKeyDailySeries(
            date=day,
            input_tokens=row.input_tokens if row else 0,
            output_tokens=row.output_tokens if row else 0,
            cache_read_tokens=row.cache_read_tokens if row else 0,
            cache_creation_tokens=row.cache_creation_tokens if row else 0,
        ))

    total_input = sum(ds.input_tokens for ds in daily_series)
    total_output = sum(ds.output_tokens for ds in daily_series)
    total_cache_read = sum(ds.cache_read_tokens for ds in daily_series)
    total_cache_creation = sum(ds.cache_creation_tokens for ds in daily_series)

    # Token usage within the selected period, per gateway key.
    usage_subq = (
        select(
            GatewayKeyDailyUsage.gateway_key_id.label("gateway_key_id"),
            func.sum(GatewayKeyDailyUsage.input_tokens).label("input_tokens"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("output_tokens"),
            func.sum(GatewayKeyDailyUsage.cache_read_tokens).label("cache_read_tokens"),
            func.sum(GatewayKeyDailyUsage.cache_creation_tokens).label("cache_creation_tokens"),
        )
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(GatewayKeyDailyUsage.gateway_key_id)
        .subquery()
    )

    # Last active timestamp is all-time (not period-bound), refreshed at most
    # once per 10 minutes per key (see increment_gateway_key_usage).
    last_used_subq = (
        select(
            GatewayKeyUsage.gateway_key_id.label("gateway_key_id"),
            func.max(GatewayKeyUsage.last_used_at).label("last_active_at"),
        )
        .group_by(GatewayKeyUsage.gateway_key_id)
        .subquery()
    )

    # All gateway-key users, with their period usage (0 if none) and last active.
    user_rows = (await session.execute(
        select(
            GatewayKey.user_id,
            User.username,
            func.coalesce(usage_subq.c.input_tokens, 0).label("input_tokens"),
            func.coalesce(usage_subq.c.output_tokens, 0).label("output_tokens"),
            func.coalesce(usage_subq.c.cache_read_tokens, 0).label("cache_read_tokens"),
            func.coalesce(usage_subq.c.cache_creation_tokens, 0).label("cache_creation_tokens"),
            last_used_subq.c.last_active_at,
        )
        .join(User, User.id == GatewayKey.user_id)
        .outerjoin(usage_subq, usage_subq.c.gateway_key_id == GatewayKey.id)
        .outerjoin(last_used_subq, last_used_subq.c.gateway_key_id == GatewayKey.id)
        .order_by(
            func.coalesce(usage_subq.c.input_tokens + usage_subq.c.output_tokens, 0).desc(),
            last_used_subq.c.last_active_at.desc().nullslast(),
        )
    )).all()

    user_usages = [
        GatewayKeyUserUsage(
            user_id=r.user_id,
            username=r.username, input_tokens=r.input_tokens, output_tokens=r.output_tokens,
            cache_read_tokens=r.cache_read_tokens, cache_creation_tokens=r.cache_creation_tokens,
            last_active_at=r.last_active_at,
        )
        for r in user_rows
    ]

    total_gw_users = len(user_usages)

    # Active = users with token usage within the selected period.
    active_gw_users = sum(1 for u in user_usages if u.input_tokens or u.output_tokens)

    return GatewayKeyAnalyticsResponse(
        time_range=range_key, total_input_tokens=total_input, total_output_tokens=total_output,
        total_cache_read_tokens=total_cache_read, total_cache_creation_tokens=total_cache_creation,
        total_gateway_users=total_gw_users, active_gateway_users=active_gw_users,
        daily_series=daily_series, user_usages=user_usages,
    )
