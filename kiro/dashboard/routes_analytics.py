from datetime import date, timedelta, timezone
from datetime import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user
from kiro.dashboard.schemas import (
    AnalyticsResponse, CreditShare, DailySeries, TopUser, UserCredit,
    KiroUserCreditUsage, KiroUserCreditUsageResponse,
    GatewayKeyDailySeries, GatewayKeyUserUsage, GatewayKeyAnalyticsResponse,
)
from kiro.db.engine import get_session
from kiro.db.models import ApiKey, DailyUsage, FallbackUsage, GatewayKey, GatewayKeyDailyUsage, GatewayKeyUsage, KeyUsage, KiroUserMapping, User

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

    # Daily series: sum credits per date across all keys
    daily_rows = (await session.execute(
        select(DailyUsage.date, func.sum(DailyUsage.credits).label("credits"))
        .where(DailyUsage.date >= start_str, DailyUsage.date <= end_str)
        .group_by(DailyUsage.date)
        .order_by(DailyUsage.date)
    )).all()

    gw_daily_rows = (await session.execute(
        select(GatewayKeyDailyUsage.date, func.sum(GatewayKeyDailyUsage.credits).label("credits"))
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(GatewayKeyDailyUsage.date)
    )).all()
    gw_daily_map = {row.date: row.credits for row in gw_daily_rows}

    daily_map = {row.date: max(0, row.credits - gw_daily_map.get(row.date, 0)) for row in daily_rows}
    daily_series = [
        DailySeries(
            date=(start + timedelta(days=i)).isoformat(),
            credits=daily_map.get((start + timedelta(days=i)).isoformat(), 0),
        )
        for i in range(days)
    ]

    # Per-kiro-user credits: join daily_usage -> api_keys (with kiro_user_id) -> aggregate
    from kiro.db.repositories import build_kiro_email_lookup, normalize_kiro_user_id

    kiro_rows = (await session.execute(
        select(ApiKey.kiro_user_id, func.sum(DailyUsage.credits).label("credits"))
        .join(DailyUsage, DailyUsage.key_id == ApiKey.id)
        .where(
            DailyUsage.date >= start_str,
            DailyUsage.date <= end_str,
            ApiKey.kiro_user_id.isnot(None),
        )
        .group_by(ApiKey.kiro_user_id)
        .order_by(func.sum(DailyUsage.credits).desc())
    )).all()

    gw_user_rows = (await session.execute(
        select(ApiKey.kiro_user_id, func.sum(GatewayKeyDailyUsage.credits).label("gw_credits"))
        .join(GatewayKeyDailyUsage, GatewayKeyDailyUsage.key_id == ApiKey.id)
        .where(
            GatewayKeyDailyUsage.date >= start_str,
            GatewayKeyDailyUsage.date <= end_str,
            ApiKey.kiro_user_id.isnot(None),
        )
        .group_by(ApiKey.kiro_user_id)
    )).all()
    gw_user_map = {row.kiro_user_id: row.gw_credits for row in gw_user_rows}

    email_lookup = await build_kiro_email_lookup(session)
    mapping_rows = (await session.execute(
        select(KiroUserMapping.kiro_user_id, KiroUserMapping.username, KiroUserMapping.email)
    )).all()
    name_map = {r.kiro_user_id: r.username or r.email or r.kiro_user_id for r in mapping_rows}

    def _display_name(kiro_uid: str) -> str:
        if kiro_uid in name_map:
            return name_map[kiro_uid]
        normalized = normalize_kiro_user_id(kiro_uid)
        for k, v in name_map.items():
            if normalize_kiro_user_id(k) == normalized:
                return v
        return email_lookup.get(kiro_uid) or email_lookup.get(normalized) or kiro_uid

    # Build merged credit map: kiro users (own usage) + gateway key users
    merged: dict[str, dict] = {}
    for r in kiro_rows:
        own_credits = max(0, r.credits - gw_user_map.get(r.kiro_user_id, 0))
        if own_credits > 0:
            merged[r.kiro_user_id] = {
                "display_name": _display_name(r.kiro_user_id),
                "credits": own_credits,
            }

    # Add gateway key user credits (keyed by "gw:<username>")
    gw_user_credit_rows = (await session.execute(
        select(
            User.username,
            func.sum(GatewayKeyDailyUsage.credits).label("credits"),
        )
        .join(GatewayKey, GatewayKey.id == GatewayKeyDailyUsage.gateway_key_id)
        .join(User, User.id == GatewayKey.user_id)
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(User.username)
        .order_by(func.sum(GatewayKeyDailyUsage.credits).desc())
    )).all()

    for r in gw_user_credit_rows:
        key = f"gw:{r.username}"
        merged[key] = {
            "display_name": f"{r.username} [GW]",
            "credits": r.credits,
        }

    sorted_merged = sorted(merged.items(), key=lambda x: x[1]["credits"], reverse=True)
    total = sum(v["credits"] for _, v in sorted_merged) or 1

    user_credits = [
        UserCredit(kiro_user_id=uid, display_name=v["display_name"], credits=v["credits"])
        for uid, v in sorted_merged
    ]
    top_users = [
        TopUser(
            rank=i + 1,
            kiro_user_id=uid,
            display_name=v["display_name"],
            credits=v["credits"],
            share_pct=round(v["credits"] / total * 100, 1),
        )
        for i, (uid, v) in enumerate(sorted_merged[:10])
    ]
    credit_share = [
        CreditShare(
            kiro_user_id=uid,
            display_name=v["display_name"],
            credits=v["credits"],
            pct=round(v["credits"] / total * 100, 1),
        )
        for uid, v in sorted_merged
    ]

    return AnalyticsResponse(
        time_range=range_key,
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


async def _aggregate_kiro_credit_usage(
    session: AsyncSession, month: str
) -> KiroUserCreditUsageResponse:
    from sqlalchemy.orm import aliased

    # Own usage: aggregate key_usage per kiro_user_id for the month
    # Sync worker writes user-level usage/limit to every key of the same user,
    # so use MAX (not SUM) for both fields
    usage_rows = (await session.execute(
        select(
            ApiKey.kiro_user_id,
            func.coalesce(func.max(KeyUsage.current_usage), 0).label("used_credit"),
            func.coalesce(func.max(KeyUsage.usage_limit), 0).label("quota"),
        )
        .outerjoin(KeyUsage, (KeyUsage.key_id == ApiKey.id) & (KeyUsage.month == month))
        .where(ApiKey.kiro_user_id.isnot(None), ApiKey.is_active == True)
        .group_by(ApiKey.kiro_user_id)
    )).all()

    usage_map: dict[str, dict] = {}
    for row in usage_rows:
        usage_map[row.kiro_user_id] = {
            "used_credit": row.used_credit,
            "quota": row.quota,
        }

    # Shared usage: credits consumed by fallback keys on behalf of this user's keys
    fallback_subq = (
        select(
            ApiKey.kiro_user_id,
            func.coalesce(func.sum(FallbackUsage.credits), 0).label("shared_usage"),
        )
        .join(FallbackUsage, FallbackUsage.original_key_id == ApiKey.id)
        .where(FallbackUsage.month == month, ApiKey.kiro_user_id.isnot(None))
        .group_by(ApiKey.kiro_user_id)
    )
    fallback_rows = (await session.execute(fallback_subq)).all()

    fallback_map: dict[str, int] = {}
    for row in fallback_rows:
        fallback_map[row.kiro_user_id] = row.shared_usage

    # Gateway usage through this user's pool keys (monthly)
    gw_pool_rows = (await session.execute(
        select(
            ApiKey.kiro_user_id,
            func.coalesce(func.sum(GatewayKeyUsage.current_usage), 0).label("gw_pool_usage"),
        )
        .join(GatewayKeyUsage, GatewayKeyUsage.key_id == ApiKey.id)
        .where(GatewayKeyUsage.month == month, ApiKey.kiro_user_id.isnot(None))
        .group_by(ApiKey.kiro_user_id)
    )).all()
    gw_pool_map: dict[str, int] = {row.kiro_user_id: row.gw_pool_usage for row in gw_pool_rows}

    # Kiro user info lookup
    mapping_rows = (await session.execute(
        select(KiroUserMapping.kiro_user_id, KiroUserMapping.username, KiroUserMapping.email)
    )).all()
    info_map = {r.kiro_user_id: (r.username, r.email) for r in mapping_rows}

    users = []
    for kiro_uid, data in usage_map.items():
        total_used = data["used_credit"]
        quota = data["quota"]
        shared = fallback_map.get(kiro_uid, 0) + gw_pool_map.get(kiro_uid, 0)
        used = max(0, total_used - shared)
        remaining = quota - total_used
        remaining_pct = round(remaining / quota * 100, 1) if quota > 0 else 0.0
        username, email = info_map.get(kiro_uid, (None, None))
        users.append(KiroUserCreditUsage(
            kiro_user_id=kiro_uid,
            username=username,
            email=email,
            used_credit=used,
            quota=quota,
            remaining=remaining,
            remaining_pct=remaining_pct,
            shared_usage=shared,
        ))

    users.sort(key=lambda u: u.used_credit, reverse=True)

    return KiroUserCreditUsageResponse(month=month, users=users)


@router.get("/analytics/kiro-credit-usage", response_model=KiroUserCreditUsageResponse)
async def get_kiro_credit_usage(
    month: str = Query(default="", pattern=r"^(\d{4}-\d{2})?$"),
    caller: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> KiroUserCreditUsageResponse:
    if not month:
        month = dt.now(timezone.utc).strftime("%Y-%m")
    return await _aggregate_kiro_credit_usage(session, month)


@router.get("/analytics/gateway-key-usage", response_model=GatewayKeyAnalyticsResponse)
async def get_gateway_key_analytics(
    range_key: str = Query(default="7d", alias="range", pattern="^(7d|30d|90d)$"),
    caller: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GatewayKeyAnalyticsResponse:
    days = _RANGE_DAYS[range_key]
    today = dt.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    start_str = start.isoformat()
    end_str = today.isoformat()

    daily_rows = (await session.execute(
        select(GatewayKeyDailyUsage.date, func.sum(GatewayKeyDailyUsage.credits).label("credits"))
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(GatewayKeyDailyUsage.date)
        .order_by(GatewayKeyDailyUsage.date)
    )).all()

    daily_map = {row.date: row.credits for row in daily_rows}
    daily_series = [
        GatewayKeyDailySeries(
            date=(start + timedelta(days=i)).isoformat(),
            credits=daily_map.get((start + timedelta(days=i)).isoformat(), 0),
        )
        for i in range(days)
    ]

    total_credits = sum(ds.credits for ds in daily_series)

    user_rows = (await session.execute(
        select(
            GatewayKey.id.label("gateway_key_id"),
            GatewayKey.user_id,
            User.username,
            func.sum(GatewayKeyDailyUsage.credits).label("credits"),
        )
        .join(GatewayKeyDailyUsage, GatewayKeyDailyUsage.gateway_key_id == GatewayKey.id)
        .join(User, User.id == GatewayKey.user_id)
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(GatewayKey.id, GatewayKey.user_id, User.username)
        .order_by(func.sum(GatewayKeyDailyUsage.credits).desc())
    )).all()

    user_usages = [
        GatewayKeyUserUsage(
            gateway_key_id=r.gateway_key_id, user_id=r.user_id,
            username=r.username, credits=r.credits,
        )
        for r in user_rows
    ]

    total_gw_users = (await session.execute(
        select(func.count()).select_from(GatewayKey)
    )).scalar_one()

    active_gw_users = len(user_usages)

    return GatewayKeyAnalyticsResponse(
        time_range=range_key, total_credits=total_credits,
        total_gateway_users=total_gw_users, active_gateway_users=active_gw_users,
        daily_series=daily_series, user_usages=user_usages,
    )
