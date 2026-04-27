from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user
from kiro.dashboard.schemas import DailyUsage, OverviewResponse
from kiro.db.engine import get_session
from kiro.db.models import ApiKey, DailyUsage as DailyUsageModel, KeyUsage, KiroUserMapping, User

router = APIRouter(prefix="/overview", tags=["overview"])


class Granularity(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


def _aggregate_weekly(daily_map: dict[str, int], start, end) -> list[DailyUsage]:
    """Aggregate daily data into ISO weeks. Label = Monday of each week."""
    from collections import defaultdict

    weekly: dict[str, int] = defaultdict(int)
    d = start
    while d <= end:
        iso_monday = d - timedelta(days=d.weekday())
        weekly[iso_monday.isoformat()] += daily_map.get(d.isoformat(), 0)
        d += timedelta(days=1)
    return [DailyUsage(date=k, credits=v) for k, v in sorted(weekly.items())]


def _aggregate_monthly(daily_map: dict[str, int], start, end) -> list[DailyUsage]:
    """Aggregate daily data into calendar months. Label = YYYY-MM."""
    from collections import defaultdict

    monthly: dict[str, int] = defaultdict(int)
    d = start
    while d <= end:
        monthly[d.strftime("%Y-%m")] += daily_map.get(d.isoformat(), 0)
        d += timedelta(days=1)
    return [DailyUsage(date=k, credits=v) for k, v in sorted(monthly.items())]


@router.get("", response_model=OverviewResponse)
async def get_overview(
    granularity: Granularity = Query(Granularity.daily),
    caller: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")

    # Total credits used & limit this month
    usage_result = await session.execute(
        select(
            func.coalesce(func.sum(KeyUsage.current_usage), 0),
            func.coalesce(func.sum(KeyUsage.usage_limit), 0),
        ).where(KeyUsage.month == current_month)
    )
    total_used, total_limit = usage_result.one()

    # Active users: distinct kiro users who consumed credits this month
    active_users = (await session.execute(
        select(func.count(func.distinct(ApiKey.kiro_user_id)))
        .join(KeyUsage, KeyUsage.key_id == ApiKey.id)
        .where(KeyUsage.month == current_month, KeyUsage.current_usage > 0)
    )).scalar_one()
    active_keys = (await session.execute(select(func.count()).where(ApiKey.is_active == True))).scalar_one()

    # Total Kiro users with at least one active API key
    total_users = (await session.execute(
        select(func.count(func.distinct(KiroUserMapping.kiro_user_id)))
        .join(ApiKey, ApiKey.kiro_user_id == KiroUserMapping.kiro_user_id)
        .where(ApiKey.is_active == True)
    )).scalar_one()

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
        select(DailyUsageModel.date, func.sum(DailyUsageModel.credits).label("credits"))
        .where(DailyUsageModel.date >= start_str, DailyUsageModel.date <= end_str)
        .group_by(DailyUsageModel.date)
        .order_by(DailyUsageModel.date)
    )).all()

    daily_map = {row.date: row.credits for row in daily_rows}

    if granularity == Granularity.weekly:
        daily_usage = _aggregate_weekly(daily_map, start_date, today)
    elif granularity == Granularity.monthly:
        daily_usage = _aggregate_monthly(daily_map, start_date, today)
    else:
        days_in_range = (today - start_date).days + 1
        daily_usage = [
            DailyUsage(
                date=(start_date + timedelta(days=i)).isoformat(),
                credits=daily_map.get((start_date + timedelta(days=i)).isoformat(), 0),
            )
            for i in range(days_in_range)
        ]

    return OverviewResponse(
        total_credits_used=int(total_used),
        total_credits_limit=int(total_limit),
        total_users=total_users,
        active_users=active_users,
        active_keys=active_keys,
        daily_usage=daily_usage,
    )
