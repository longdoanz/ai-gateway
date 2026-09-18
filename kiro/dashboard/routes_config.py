import json

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import require_admin
from kiro.dashboard.schemas import SystemConfigResponse, SystemConfigUpdate
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import get_all_config, set_config

router = APIRouter(prefix="/config", tags=["config"])

CONFIG_DEFAULTS = {
    "enable_nine_router_model_override": "false",
    "nine_router_model_override_rules": "[]",
    "nine_router_model_override_default": "auto",
}

_NINE_ROUTER_OVERRIDE_KEYS = {"enable_nine_router_model_override", "nine_router_model_override_rules", "nine_router_model_override_default"}

_PII_GUARD_KEYS = {"pii_guard_mode", "pii_secret_action", "pii_restore_tool_args"}


def _pii_defaults() -> dict[str, str]:
    """Fall back to .env for any PII key the dashboard has never written.

    Read at call time rather than folded into CONFIG_DEFAULTS: those are module
    constants, and the guard's own resolver (``kiro.guardrails.get_pii_policy``)
    applies the same .env-as-floor rule. Both sides must agree, or the UI would
    show a state the gateway is not actually in.
    """
    from kiro.config import PII_GUARD_MODE, PII_RESTORE_TOOL_ARGS, PII_SECRET_ACTION

    return {
        "pii_guard_mode": PII_GUARD_MODE,
        "pii_secret_action": PII_SECRET_ACTION,
        "pii_restore_tool_args": str(PII_RESTORE_TOOL_ARGS).lower(),
    }


def _to_response(raw: dict[str, str]) -> SystemConfigResponse:
    merged = {**CONFIG_DEFAULTS, **_pii_defaults(), **raw}
    from kiro.model_override import _parse_rules
    nr_rules_raw = _parse_rules(merged.get("nine_router_model_override_rules", "[]"))
    return SystemConfigResponse(
        enable_nine_router_model_override=merged["enable_nine_router_model_override"].lower() == "true",
        nine_router_model_override_rules=nr_rules_raw,
        nine_router_model_override_default=merged.get("nine_router_model_override_default", "auto"),
        pii_guard_mode=merged["pii_guard_mode"],
        pii_secret_action=merged["pii_secret_action"],
        pii_restore_tool_args=merged["pii_restore_tool_args"].lower() == "true",
    )


@router.get("", response_model=SystemConfigResponse, response_model_by_alias=True)
async def get_config_route(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    raw = await get_all_config(session)
    return _to_response(raw)


@router.put("", response_model=SystemConfigResponse, response_model_by_alias=True)
async def update_config_route(body: SystemConfigUpdate, admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    updates = body.model_dump(exclude_unset=True, by_alias=True)
    for key, value in updates.items():
        if isinstance(value, bool):
            str_value = str(value).lower()
        elif isinstance(value, list):
            str_value = json.dumps(value)  # already dicts with "from" key via by_alias=True
        else:
            str_value = str(value)
        await set_config(session, key, str_value)
    raw = await get_all_config(session)
    if _NINE_ROUTER_OVERRIDE_KEYS & set(updates.keys()):
        from kiro.nine_router_client import invalidate_nine_router_override_cache
        invalidate_nine_router_override_cache()
    if _PII_GUARD_KEYS & set(updates.keys()):
        # The point of a UI switch is stopping a misbehaving guard while
        # traffic is flowing, so it has to take effect without a restart.
        from kiro.guardrails import invalidate_pii_guard_cache
        invalidate_pii_guard_cache()
        policy = _to_response(raw)
        logger.warning(
            f"PII guard: policy changed by {admin.username} -> mode={policy.pii_guard_mode} "
            f"secrets={policy.pii_secret_action} tool_args={policy.pii_restore_tool_args}"
        )
    return _to_response(raw)
