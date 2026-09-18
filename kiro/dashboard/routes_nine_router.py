"""
Dashboard endpoint: expose 9router's live model catalog for the admin UI's
model picker (e.g. when configuring a Service Account's allowed_models).
"""

from fastapi import APIRouter, Depends

from kiro.dashboard.deps import require_admin
from kiro.dashboard.schemas import NineRouterModelListResponse
from kiro.db.models import User
from kiro.nine_router_client import fetch_nine_router_models

router = APIRouter(prefix="/nine-router", tags=["nine-router"])


@router.get("/models", response_model=NineRouterModelListResponse)
async def list_nine_router_models(admin: User = Depends(require_admin)):
    """Return the live catalog of model ids that 9router can route to."""
    models = await fetch_nine_router_models()
    return NineRouterModelListResponse(models=models, total=len(models))
