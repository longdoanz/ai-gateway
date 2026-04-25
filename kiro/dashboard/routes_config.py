from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import require_admin
from kiro.dashboard.schemas import SystemConfigResponse, SystemConfigUpdate
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import get_all_config, set_config

router = APIRouter(prefix="/config", tags=["config"])

CONFIG_DEFAULTS = {
    "enable_model_override": "false",
    "enforced_global_model": "auto",
    "enable_usage_sharing": "false",
}


def _to_response(raw: dict[str, str]) -> SystemConfigResponse:
    merged = {**CONFIG_DEFAULTS, **raw}
    return SystemConfigResponse(
        enable_model_override=merged["enable_model_override"].lower() == "true",
        enforced_global_model=merged["enforced_global_model"],
        enable_usage_sharing=merged["enable_usage_sharing"].lower() == "true",
    )


@router.get("", response_model=SystemConfigResponse)
async def get_config_route(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    raw = await get_all_config(session)
    return _to_response(raw)


@router.put("", response_model=SystemConfigResponse)
async def update_config_route(body: SystemConfigUpdate, admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        str_value = str(value).lower() if isinstance(value, bool) else str(value)
        await set_config(session, key, str_value)
    raw = await get_all_config(session)
    return _to_response(raw)
