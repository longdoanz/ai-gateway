from datetime import date, timedelta, timezone
from datetime import datetime as dt

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
