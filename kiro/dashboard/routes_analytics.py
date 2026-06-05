from datetime import date, timedelta, timezone
from datetime import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user
from kiro.dashboard.schemas import (
    AnalyticsResponse, TokenShare, DailySeries, TopUser, UserTokenUsage, UserDailySeries,
    KiroUserCreditUsage, KiroUserCreditUsageResponse,
    GatewayKeyDailySeries, GatewayKeyUserUsage, GatewayKeyAnalyticsResponse,
)
from kiro.db.engine import get_session
from kiro.db.models import ApiKey, DailyUsage, FallbackUsage, GatewayKey, GatewayKeyDailyUsage, KeyUsage, KiroUserMapping, User

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
    # resolves to a concrete kiro key_id, so GatewayKeyDailyUsage.key_id is never NULL.
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

    from kiro.db.repositories import build_kiro_email_lookup, normalize_kiro_user_id

    # --- Build kiro user info maps ---
    mapping_rows = (await session.execute(
        select(KiroUserMapping.kiro_user_id, KiroUserMapping.username, KiroUserMapping.email)
    )).all()

    # kiro_user_id -> (username, email)
    kiro_info: dict[str, tuple[str | None, str | None]] = {}
    for r in mapping_rows:
        kiro_info[r.kiro_user_id] = (r.username, r.email)
        normalized = normalize_kiro_user_id(r.kiro_user_id)
        if normalized != r.kiro_user_id:
            kiro_info[normalized] = (r.username, r.email)

    # Enrich kiro_info from ApiKey->User link so kiro users with a gateway account
    # share the same merge key (email or username) as their gateway counterpart.
    apikey_user_rows = (await session.execute(
        select(ApiKey.kiro_user_id, User.username, User.email)
        .join(User, User.id == ApiKey.user_id)
        .where(ApiKey.kiro_user_id.isnot(None), ApiKey.user_id.isnot(None))
    )).all()
    for r in apikey_user_rows:
        # Always prefer User data when there's a direct ApiKey link — this ensures
        # the kiro merge key matches the gateway merge key for the same person.
        kiro_info[r.kiro_user_id] = (r.username, r.email)
        normalized = normalize_kiro_user_id(r.kiro_user_id)
        if normalized != r.kiro_user_id:
            kiro_info[normalized] = (r.username, r.email)

    email_lookup = await build_kiro_email_lookup(session)

    def _kiro_display(kiro_uid: str, username: str | None, email: str | None) -> str:
        if username:
            return username
        if email:
            return email
        normalized = normalize_kiro_user_id(kiro_uid)
        return email_lookup.get(kiro_uid) or email_lookup.get(normalized) or normalized or kiro_uid

    # --- Kiro user token totals (pool key usage) ---
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
    )).all()

    # Gateway pool-key usage attributed to kiro users (to subtract double-count)
    gw_pool_user_rows = (await session.execute(
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
    gw_pool_user_map = {row.kiro_user_id: (row.gw_input, row.gw_output) for row in gw_pool_user_rows}

    # --- Gateway user token totals ---
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

    def _merge_key_for_kiro(kiro_uid: str) -> str:
        username, email = kiro_info.get(kiro_uid) or kiro_info.get(normalize_kiro_user_id(kiro_uid)) or (None, None)
        if email:
            return email.lower()
        if username:
            return username.lower()
        return normalize_kiro_user_id(kiro_uid) or kiro_uid

    for r in kiro_rows:
        gw_in, gw_out = gw_pool_user_map.get(r.kiro_user_id, (0, 0))
        own_in = max(0, r.input_tokens - gw_in)
        own_out = max(0, r.output_tokens - gw_out)
        if own_in <= 0 and own_out <= 0:
            continue
        normalized = normalize_kiro_user_id(r.kiro_user_id)
        username, email = kiro_info.get(r.kiro_user_id) or kiro_info.get(normalized) or (None, None)
        key = _merge_key_for_kiro(r.kiro_user_id)
        if key in merged:
            merged[key]["input_tokens"] += own_in
            merged[key]["output_tokens"] += own_out
        else:
            merged[key] = {
                "display_name": _kiro_display(r.kiro_user_id, username, email),
                "username": username,
                "email": email,
                "input_tokens": own_in,
                "output_tokens": own_out,
            }

    for r in gw_user_token_rows:
        email = r.email
        username = r.username
        key = (email.lower() if email else None) or (username.lower() if username else None)
        if not key:
            continue
        if key in merged:
            merged[key]["input_tokens"] += r.input_tokens
            merged[key]["output_tokens"] += r.output_tokens
            # fill in email/username if missing from kiro side
            if not merged[key]["email"] and email:
                merged[key]["email"] = email
            if not merged[key]["username"] and username:
                merged[key]["username"] = username
        else:
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
            kiro_user_id=uid,
            display_name=v["display_name"],
            username=v.get("username"),
            email=v.get("email"),
            input_tokens=v["input_tokens"],
            output_tokens=v["output_tokens"],
        )
        for uid, v in sorted_merged
    ]
    top_users = [
        TopUser(
            rank=i + 1,
            kiro_user_id=uid,
            display_name=v["display_name"],
            username=v.get("username"),
            email=v.get("email"),
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
            username=v.get("username"),
            email=v.get("email"),
            input_tokens=v["input_tokens"],
            output_tokens=v["output_tokens"],
            pct=round((v["input_tokens"] + v["output_tokens"]) / total * 100, 1),
        )
        for uid, v in sorted_merged
    ]

    # --- Per-user daily series (top 10) ---
    top_keys = [uid for uid, _ in sorted_merged[:10]]

    kiro_daily_rows = (await session.execute(
        select(
            ApiKey.kiro_user_id,
            DailyUsage.date,
            func.sum(DailyUsage.input_tokens).label("input_tokens"),
            func.sum(DailyUsage.output_tokens).label("output_tokens"),
        )
        .join(DailyUsage, DailyUsage.key_id == ApiKey.id)
        .where(
            DailyUsage.date >= start_str,
            DailyUsage.date <= end_str,
            ApiKey.kiro_user_id.isnot(None),
        )
        .group_by(ApiKey.kiro_user_id, DailyUsage.date)
    )).all()

    # Pool-key gateway usage per kiro user per date (to subtract double-count in daily series)
    gw_pool_daily_rows = (await session.execute(
        select(
            ApiKey.kiro_user_id,
            GatewayKeyDailyUsage.date,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("gw_input"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("gw_output"),
        )
        .join(GatewayKeyDailyUsage, GatewayKeyDailyUsage.key_id == ApiKey.id)
        .where(
            GatewayKeyDailyUsage.date >= start_str,
            GatewayKeyDailyUsage.date <= end_str,
            ApiKey.kiro_user_id.isnot(None),
        )
        .group_by(ApiKey.kiro_user_id, GatewayKeyDailyUsage.date)
    )).all()
    # (kiro_user_id, date) -> (gw_input, gw_output)
    gw_pool_daily_map: dict[tuple[str, str], tuple[int, int]] = {}
    for r in gw_pool_daily_rows:
        gw_pool_daily_map[(r.kiro_user_id, r.date)] = (r.gw_input, r.gw_output)

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

    for r in kiro_daily_rows:
        key = _merge_key_for_kiro(r.kiro_user_id)
        if key not in top_keys:
            continue
        gw_in_day, gw_out_day = gw_pool_daily_map.get((r.kiro_user_id, r.date), (0, 0))
        own_in = max(0, r.input_tokens - gw_in_day)
        own_out = max(0, r.output_tokens - gw_out_day)
        if key not in user_date_map:
            user_date_map[key] = {}
        prev_in, prev_out = user_date_map[key].get(r.date, (0, 0))
        user_date_map[key][r.date] = (prev_in + own_in, prev_out + own_out)

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
        .where(ApiKey.kiro_user_id.isnot(None), ApiKey.is_active == True, ApiKey.is_system == False)
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
        .where(FallbackUsage.month == month, ApiKey.kiro_user_id.isnot(None), ApiKey.is_system == False)
        .group_by(ApiKey.kiro_user_id)
    )
    fallback_rows = (await session.execute(fallback_subq)).all()

    fallback_map: dict[str, tuple[int, int]] = {}
    for row in fallback_rows:
        fallback_map[row.kiro_user_id] = (row.shared_input, row.shared_output)

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
        remaining = quota - total_used
        remaining_pct = round(remaining / quota * 100, 1) if quota > 0 else 0.0
        normalized = normalize_kiro_user_id(kiro_uid)
        username, email = info_map.get(kiro_uid) or info_map.get(normalized) or (None, None)
        users.append(KiroUserCreditUsage(
            kiro_user_id=kiro_uid,
            display_name=_display_name(kiro_uid, username, email),
            username=username,
            email=email,
            used_credit=total_used,
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
            GatewayKey.user_id,
            User.username,
            func.sum(GatewayKeyDailyUsage.input_tokens).label("input_tokens"),
            func.sum(GatewayKeyDailyUsage.output_tokens).label("output_tokens"),
        )
        .join(GatewayKeyDailyUsage, GatewayKeyDailyUsage.gateway_key_id == GatewayKey.id)
        .join(User, User.id == GatewayKey.user_id)
        .where(GatewayKeyDailyUsage.date >= start_str, GatewayKeyDailyUsage.date <= end_str)
        .group_by(GatewayKey.user_id, User.username)
        .order_by(func.sum(GatewayKeyDailyUsage.input_tokens + GatewayKeyDailyUsage.output_tokens).desc())
    )).all()

    user_usages = [
        GatewayKeyUserUsage(
            user_id=r.user_id,
            username=r.username, input_tokens=r.input_tokens, output_tokens=r.output_tokens,
        )
        for r in user_rows
    ]

    total_gw_users = (await session.execute(
        select(func.count(func.distinct(GatewayKey.user_id))).select_from(GatewayKey)
    )).scalar_one()

    active_gw_users = len(user_usages)

    return GatewayKeyAnalyticsResponse(
        time_range=range_key, total_input_tokens=total_input, total_output_tokens=total_output,
        total_gateway_users=total_gw_users, active_gateway_users=active_gw_users,
        daily_series=daily_series, user_usages=user_usages,
    )
