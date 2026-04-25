from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user
from kiro.dashboard.schemas import DailyUsage, OverviewResponse
from kiro.db.engine import get_session
from kiro.db.models import ApiKey, KeyUsage, User

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("", response_model=OverviewResponse)
async def get_overview(caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    current_month = datetime.utcnow().strftime("%Y-%m")

    # Total credits used & limit this month
    usage_result = await session.execute(
        select(
            func.coalesce(func.sum(KeyUsage.current_usage), 0),
            func.coalesce(func.sum(KeyUsage.usage_limit), 0),
        ).where(KeyUsage.month == current_month)
    )
    total_used, total_limit = usage_result.one()

    # Active users & keys
    active_users = (await session.execute(select(func.count()).where(User.is_active == True))).scalar_one()
    active_keys = (await session.execute(select(func.count()).where(ApiKey.is_active == True))).scalar_one()

    # Daily usage for last 30 days (from key_usage.last_used_at grouped by date)
    # Simplified: return per-month data split into daily placeholder
    # Real daily tracking would need a separate daily_usage table — for now aggregate monthly
    daily_usage = [DailyUsage(date=current_month, credits=int(total_used))]

    return OverviewResponse(
        total_credits_used=int(total_used),
        total_credits_limit=int(total_limit),
        active_users=active_users,
        active_keys=active_keys,
        daily_usage=daily_usage,
    )
