from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user
from kiro.dashboard.schemas import CreditTrendPoint, DailyUsage, OverviewResponse
from kiro.db.engine import get_session
from kiro.db.models import ApiKey, DailyUsage as DailyUsageModel, GatewayKey, GatewayKeyDailyUsage, GatewayKeyUsage, KeyUsage, KiroUserMapping, User
from kiro.db.repositories import get_credit_snapshots

router = APIRouter(prefix="/overview", tags=["overview"])


class Granularity(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


def _aggregate_weekly(daily_map: dict[str, tuple[int, int]], start, end) -> list[DailyUsage]:
    """Aggregate daily data into ISO weeks. Label = Monday of each week."""
    from collections import defaultdict

    weekly: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    d = start
    while d <= end:
        iso_monday = d - timedelta(days=d.weekday())
        key = iso_monday.isoformat()
        in_tok, out_tok = daily_map.get(d.isoformat(), (0, 0))
        weekly[key][0] += in_tok
        weekly[key][1] += out_tok
        d += timedelta(days=1)
    return [DailyUsage(date=k, input_tokens=v[0], output_tokens=v[1]) for k, v in sorted(weekly.items())]


def _aggregate_monthly(daily_map: dict[str, tuple[int, int]], start, end) -> list[DailyUsage]:
    """Aggregate daily data into calendar months. Label = YYYY-MM."""
    from collections import defaultdict

    monthly: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    d = start
    while d <= end:
        key = d.strftime("%Y-%m")
        in_tok, out_tok = daily_map.get(d.isoformat(), (0, 0))
        monthly[key][0] += in_tok
        monthly[key][1] += out_tok
        d += timedelta(days=1)
    return [DailyUsage(date=k, input_tokens=v[0], output_tokens=v[1]) for k, v in sorted(monthly.items())]


@router.get("", response_model=OverviewResponse)
async def get_overview(
    granularity: Granularity = Query(Granularity.daily),
    caller: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")

    # Total credits used & limit this month (MAX per user to avoid double-counting)
    per_user_subq = (
        select(
            ApiKey.kiro_user_id,
            func.max(KeyUsage.current_usage).label("current_usage"),
            func.max(KeyUsage.usage_limit).label("usage_limit"),
        )
        .join(ApiKey, ApiKey.id == KeyUsage.key_id)
        .where(KeyUsage.month == current_month, ApiKey.kiro_user_id.isnot(None))
        .group_by(ApiKey.kiro_user_id)
        .subquery()
    )
    usage_result = await session.execute(
        select(
            func.coalesce(func.sum(per_user_subq.c.current_usage), 0),
            func.coalesce(func.sum(per_user_subq.c.usage_limit), 0),
        )
    )
    total_used, total_limit = usage_result.one()

    # Active users: distinct kiro users who consumed credits this month
    active_kiro_users = (await session.execute(
        select(func.count(func.distinct(ApiKey.kiro_user_id)))
        .join(KeyUsage, KeyUsage.key_id == ApiKey.id)
        .where(KeyUsage.month == current_month, KeyUsage.current_usage > 0)
    )).scalar_one()
    active_gw_users = (await session.execute(
        select(func.count(func.distinct(GatewayKeyUsage.gateway_key_id)))
        .where(GatewayKeyUsage.month == current_month, GatewayKeyUsage.current_usage > 0)
    )).scalar_one()
    active_users = active_kiro_users + active_gw_users
    active_keys = (await session.execute(select(func.count()).where(ApiKey.is_active == True))).scalar_one()

    # Total Kiro users with at least one active API key + gateway key users
    total_kiro_users = (await session.execute(
        select(func.count(func.distinct(KiroUserMapping.kiro_user_id)))
        .join(ApiKey, ApiKey.kiro_user_id == KiroUserMapping.kiro_user_id)
        .where(ApiKey.is_active == True)
    )).scalar_one()
    total_gw_users = (await session.execute(
        select(func.count()).select_from(GatewayKey).where(GatewayKey.is_active == True)
    )).scalar_one()
    total_users = total_kiro_users + total_gw_users

    # Date range: for weekly/monthly we go back further to have meaningful data
    today = datetime.now(timezone.utc).date()
    if granularity == Granularity.monthly:
        start_date = (today.replace(day=1) - timedelta(days=180)).replace(day=1)  # ~6 months
    elif granularity == Granularity.weekly:
        start_date = today - timedelta(days=90)
    else:
        start_date = today.replace(day=1)

    start_str = start_date.isoformat()
    end_str = today.isoformat()

    daily_rows = (await session.execute(
        select(
            DailyUsageModel.date,
            func.sum(DailyUsageModel.input_tokens).label("input_tokens"),
            func.sum(DailyUsageModel.output_tokens).label("output_tokens"),
        )
        .where(DailyUsageModel.date >= start_str, DailyUsageModel.date <= end_str)
        .group_by(DailyUsageModel.date)
        .order_by(DailyUsageModel.date)
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

    daily_map: dict[str, tuple[int, int]] = {}
    for row in daily_rows:
        gw_in, gw_out = gw_daily_map.get(row.date, (0, 0))
        daily_map[row.date] = (max(0, row.input_tokens - gw_in), max(0, row.output_tokens - gw_out))

    if granularity == Granularity.weekly:
        daily_usage = _aggregate_weekly(daily_map, start_date, today)
    elif granularity == Granularity.monthly:
        daily_usage = _aggregate_monthly(daily_map, start_date, today)
    else:
        days_in_range = (today - start_date).days + 1
        daily_usage = [
            DailyUsage(
                date=(start_date + timedelta(days=i)).isoformat(),
                input_tokens=daily_map.get((start_date + timedelta(days=i)).isoformat(), (0, 0))[0],
                output_tokens=daily_map.get((start_date + timedelta(days=i)).isoformat(), (0, 0))[1],
            )
            for i in range(days_in_range)
        ]

    # Gateway token totals for this month
    gw_token_result = await session.execute(
        select(
            func.coalesce(func.sum(GatewayKeyDailyUsage.input_tokens), 0),
            func.coalesce(func.sum(GatewayKeyDailyUsage.output_tokens), 0),
        )
        .where(GatewayKeyDailyUsage.date >= today.replace(day=1).isoformat(), GatewayKeyDailyUsage.date <= end_str)
    )
    gw_input_total, gw_output_total = gw_token_result.one()

    # Own token totals for this month
    own_token_result = await session.execute(
        select(
            func.coalesce(func.sum(DailyUsageModel.input_tokens), 0),
            func.coalesce(func.sum(DailyUsageModel.output_tokens), 0),
        )
        .where(DailyUsageModel.date >= today.replace(day=1).isoformat(), DailyUsageModel.date <= end_str)
    )
    total_input, total_output = own_token_result.one()

    # Credit trend: daily deltas from snapshots
    snapshot_start = (start_date - timedelta(days=1)).isoformat()
    snapshots = await get_credit_snapshots(session, snapshot_start, end_str)
    credit_trend: list[CreditTrendPoint] = []
    for i in range(1, len(snapshots)):
        prev_date, prev_total = snapshots[i - 1]
        cur_date, cur_total = snapshots[i]
        delta = max(0, cur_total - prev_total)
        credit_trend.append(CreditTrendPoint(date=cur_date, credits_used=delta))

    return OverviewResponse(
        total_input_tokens=int(total_input),
        total_output_tokens=int(total_output),
        total_credits_used=int(total_used),
        total_credits_limit=int(total_limit),
        total_users=total_users,
        active_users=active_users,
        active_keys=active_keys,
        daily_usage=daily_usage,
        credit_trend=credit_trend,
        total_gateway_users=(await session.execute(
            select(func.count()).select_from(GatewayKey).where(GatewayKey.is_active == True)
        )).scalar_one(),
        active_gateway_users=(await session.execute(
            select(func.count(func.distinct(GatewayKeyUsage.gateway_key_id)))
            .where(GatewayKeyUsage.month == current_month, GatewayKeyUsage.current_usage > 0)
        )).scalar_one(),
        gateway_input_tokens=int(gw_input_total),
        gateway_output_tokens=int(gw_output_total),
    )
