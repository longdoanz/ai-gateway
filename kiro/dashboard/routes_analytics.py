from datetime import date, timedelta, timezone
from datetime import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user
from kiro.dashboard.schemas import (
    AnalyticsResponse, CreditShare, DailySeries, TopUser, UserCredit,
    KiroUserCreditUsage, KiroUserCreditUsageResponse,
)
from kiro.db.engine import get_session
from kiro.db.models import ApiKey, DailyUsage, FallbackUsage, KeyUsage, KiroUserMapping, User

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

    daily_map = {row.date: row.credits for row in daily_rows}
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

    total = sum(r.credits for r in kiro_rows) or 1

    user_credits = [
        UserCredit(kiro_user_id=r.kiro_user_id, display_name=_display_name(r.kiro_user_id), credits=r.credits)
        for r in kiro_rows
    ]
    top_users = [
        TopUser(
            rank=i + 1,
            kiro_user_id=r.kiro_user_id,
            display_name=_display_name(r.kiro_user_id),
            credits=r.credits,
            share_pct=round(r.credits / total * 100, 1),
        )
        for i, r in enumerate(kiro_rows[:10])
    ]
    credit_share = [
        CreditShare(
            kiro_user_id=r.kiro_user_id,
            display_name=_display_name(r.kiro_user_id),
            credits=r.credits,
            pct=round(r.credits / total * 100, 1),
        )
        for r in kiro_rows
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

    # Kiro user info lookup
    mapping_rows = (await session.execute(
        select(KiroUserMapping.kiro_user_id, KiroUserMapping.username, KiroUserMapping.email)
    )).all()
    info_map = {r.kiro_user_id: (r.username, r.email) for r in mapping_rows}

    users = []
    for kiro_uid, data in usage_map.items():
        used = data["used_credit"]
        quota = data["quota"]
        remaining = quota - used
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
            shared_usage=fallback_map.get(kiro_uid, 0),
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
