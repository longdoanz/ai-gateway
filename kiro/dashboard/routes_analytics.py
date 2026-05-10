from datetime import date, timedelta, timezone
from datetime import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user
from kiro.dashboard.schemas import (
    AnalyticsResponse, TokenShare, DailySeries, TopUser, UserTokenUsage,
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

    gw_daily_rows = (await session.execute(
        select(
            GatewayKeyDailyUsage.date,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("input_tokens"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("output_tokens"),
        )
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(GatewayKeyDailyUsage.date)
    )).all()
    gw_daily_map = {row.date: (row.input_tokens, row.output_tokens) for row in gw_daily_rows}

    daily_map = {}
    for row in daily_rows:
        gw_in, gw_out = gw_daily_map.get(row.date, (0, 0))
        daily_map[row.date] = (max(0, row.input_tokens - gw_in), max(0, row.output_tokens - gw_out))

    daily_series = [
        DailySeries(
            date=(start + timedelta(days=i)).isoformat(),
            input_tokens=daily_map.get((start + timedelta(days=i)).isoformat(), (0, 0))[0],
            output_tokens=daily_map.get((start + timedelta(days=i)).isoformat(), (0, 0))[1],
        )
        for i in range(days)
    ]

    from kiro.db.repositories import build_kiro_email_lookup, normalize_kiro_user_id

    kiro_rows = (await session.execute(
        select(
            ApiKey.kiro_user_id,
            func.sum(DailyUsage.input_tokens).label("input_tokens"),
            func.sum(DailyUsage.output_tokens).label("output_tokens"),
        )
        .join(DailyUsage, DailyUsage.key_id == ApiKey.id)
        .where(
            DailyUsage.date >= start_str,
            DailyUsage.date <= end_str,
            ApiKey.kiro_user_id.isnot(None),
        )
        .group_by(ApiKey.kiro_user_id)
        .order_by(func.sum(DailyUsage.input_tokens + DailyUsage.output_tokens).desc())
    )).all()

    gw_user_rows = (await session.execute(
        select(
            ApiKey.kiro_user_id,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("gw_input"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("gw_output"),
        )
        .join(GatewayKeyDailyUsage, GatewayKeyDailyUsage.key_id == ApiKey.id)
        .where(
            GatewayKeyDailyUsage.date >= start_str,
            GatewayKeyDailyUsage.date <= end_str,
            ApiKey.kiro_user_id.isnot(None),
        )
        .group_by(ApiKey.kiro_user_id)
    )).all()
    gw_user_map = {row.kiro_user_id: (row.gw_input, row.gw_output) for row in gw_user_rows}

    email_lookup = await build_kiro_email_lookup(session)
    mapping_rows = (await session.execute(
        select(KiroUserMapping.kiro_user_id, KiroUserMapping.username, KiroUserMapping.email)
    )).all()
    name_map: dict[str, str] = {}
    for r in mapping_rows:
        name = r.username or r.email
        if not name:
            continue
        name_map[r.kiro_user_id] = name
        normalized = normalize_kiro_user_id(r.kiro_user_id)
        if normalized != r.kiro_user_id:
            name_map[normalized] = name

    def _display_name(kiro_uid: str) -> str:
        if kiro_uid in name_map:
            return name_map[kiro_uid]
        normalized = normalize_kiro_user_id(kiro_uid)
        if normalized in name_map:
            return name_map[normalized]
        return email_lookup.get(kiro_uid) or email_lookup.get(normalized) or kiro_uid

    merged: dict[str, dict] = {}
    for r in kiro_rows:
        gw_in, gw_out = gw_user_map.get(r.kiro_user_id, (0, 0))
        own_in = max(0, r.input_tokens - gw_in)
        own_out = max(0, r.output_tokens - gw_out)
        if own_in > 0 or own_out > 0:
            merged[r.kiro_user_id] = {
                "display_name": _display_name(r.kiro_user_id),
                "input_tokens": own_in,
                "output_tokens": own_out,
            }

    gw_user_token_rows = (await session.execute(
        select(
            User.username,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("input_tokens"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("output_tokens"),
        )
        .join(GatewayKey, GatewayKey.id == GatewayKeyDailyUsage.gateway_key_id)
        .join(User, User.id == GatewayKey.user_id)
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(User.username)
        .order_by(func.sum(GatewayKeyDailyUsage.input_tokens + GatewayKeyDailyUsage.output_tokens).desc())
    )).all()

    for r in gw_user_token_rows:
        key = f"gw:{r.username}"
        merged[key] = {
            "display_name": f"{r.username} [GW]",
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
        }

    sorted_merged = sorted(merged.items(), key=lambda x: x[1]["input_tokens"] + x[1]["output_tokens"], reverse=True)
    total = sum(v["input_tokens"] + v["output_tokens"] for _, v in sorted_merged) or 1

    user_tokens = [
        UserTokenUsage(kiro_user_id=uid, display_name=v["display_name"], input_tokens=v["input_tokens"], output_tokens=v["output_tokens"])
        for uid, v in sorted_merged
    ]
    top_users = [
        TopUser(
            rank=i + 1,
            kiro_user_id=uid,
            display_name=v["display_name"],
            input_tokens=v["input_tokens"],
            output_tokens=v["output_tokens"],
            share_pct=round((v["input_tokens"] + v["output_tokens"]) / total * 100, 1),
        )
        for i, (uid, v) in enumerate(sorted_merged[:10])
    ]
    token_share = [
        TokenShare(
            kiro_user_id=uid,
            display_name=v["display_name"],
            input_tokens=v["input_tokens"],
            output_tokens=v["output_tokens"],
            pct=round((v["input_tokens"] + v["output_tokens"]) / total * 100, 1),
        )
        for uid, v in sorted_merged
    ]

    return AnalyticsResponse(
        time_range=range_key,
        daily_series=daily_series,
        user_tokens=user_tokens,
        top_users=top_users,
        token_share=token_share,
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
    from kiro.db.repositories import normalize_kiro_user_id

    def _display_name(kiro_uid: str, username: str | None, email: str | None) -> str:
        if username:
            return username
        if email:
            return email
        normalized = normalize_kiro_user_id(kiro_uid)
        return normalized or kiro_uid

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

    # Shared usage: tokens consumed by fallback keys on behalf of this user's keys
    fallback_subq = (
        select(
            ApiKey.kiro_user_id,
            func.coalesce(func.sum(FallbackUsage.input_tokens), 0).label("shared_input"),
            func.coalesce(func.sum(FallbackUsage.output_tokens), 0).label("shared_output"),
        )
        .join(FallbackUsage, FallbackUsage.original_key_id == ApiKey.id)
        .where(FallbackUsage.month == month, ApiKey.kiro_user_id.isnot(None))
        .group_by(ApiKey.kiro_user_id)
    )
    fallback_rows = (await session.execute(fallback_subq)).all()

    fallback_map: dict[str, tuple[int, int]] = {}
    for row in fallback_rows:
        fallback_map[row.kiro_user_id] = (row.shared_input, row.shared_output)

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

    mapping_rows = (await session.execute(
        select(KiroUserMapping.kiro_user_id, KiroUserMapping.username, KiroUserMapping.email)
    )).all()
    info_map: dict[str, tuple[str | None, str | None]] = {}
    for r in mapping_rows:
        info_map[r.kiro_user_id] = (r.username, r.email)
        normalized = normalize_kiro_user_id(r.kiro_user_id)
        if normalized != r.kiro_user_id:
            info_map[normalized] = (r.username, r.email)

    users = []
    for kiro_uid, data in usage_map.items():
        total_used = data["used_credit"]
        quota = data["quota"]
        shared_in, shared_out = fallback_map.get(kiro_uid, (0, 0))
        gw_pool = gw_pool_map.get(kiro_uid, 0)
        shared_total = shared_in + shared_out + gw_pool
        used = max(0, total_used - shared_total)
        remaining = quota - total_used
        remaining_pct = round(remaining / quota * 100, 1) if quota > 0 else 0.0
        normalized = normalize_kiro_user_id(kiro_uid)
        username, email = info_map.get(kiro_uid) or info_map.get(normalized) or (None, None)
        users.append(KiroUserCreditUsage(
            kiro_user_id=kiro_uid,
            display_name=_display_name(kiro_uid, username, email),
            username=username,
            email=email,
            used_credit=used,
            quota=quota,
            remaining=remaining,
            remaining_pct=remaining_pct,
            shared_input_tokens=shared_in,
            shared_output_tokens=shared_out,
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
        select(
            GatewayKeyDailyUsage.date,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("input_tokens"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("output_tokens"),
        )
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(GatewayKeyDailyUsage.date)
        .order_by(GatewayKeyDailyUsage.date)
    )).all()

    daily_map = {row.date: (row.input_tokens, row.output_tokens) for row in daily_rows}
    daily_series = [
        GatewayKeyDailySeries(
            date=(start + timedelta(days=i)).isoformat(),
            input_tokens=daily_map.get((start + timedelta(days=i)).isoformat(), (0, 0))[0],
            output_tokens=daily_map.get((start + timedelta(days=i)).isoformat(), (0, 0))[1],
        )
        for i in range(days)
    ]

    total_input = sum(ds.input_tokens for ds in daily_series)
    total_output = sum(ds.output_tokens for ds in daily_series)

    user_rows = (await session.execute(
        select(
            GatewayKey.id.label("gateway_key_id"),
            GatewayKey.user_id,
            User.username,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("input_tokens"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("output_tokens"),
        )
        .join(GatewayKeyDailyUsage, GatewayKeyDailyUsage.gateway_key_id == GatewayKey.id)
        .join(User, User.id == GatewayKey.user_id)
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(GatewayKey.id, GatewayKey.user_id, User.username)
        .order_by(func.sum(GatewayKeyDailyUsage.input_tokens + GatewayKeyDailyUsage.output_tokens).desc())
    )).all()

    user_usages = [
        GatewayKeyUserUsage(
            gateway_key_id=r.gateway_key_id, user_id=r.user_id,
            username=r.username, input_tokens=r.input_tokens, output_tokens=r.output_tokens,
        )
        for r in user_rows
    ]

    total_gw_users = (await session.execute(
        select(func.count()).select_from(GatewayKey)
    )).scalar_one()

    active_gw_users = len(user_usages)

    return GatewayKeyAnalyticsResponse(
        time_range=range_key, total_input_tokens=total_input, total_output_tokens=total_output,
        total_gateway_users=total_gw_users, active_gateway_users=active_gw_users,
        daily_series=daily_series, user_usages=user_usages,
    )
