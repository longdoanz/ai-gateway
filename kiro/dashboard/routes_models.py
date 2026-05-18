"""
Dashboard endpoint: list available models for dropdowns.

Reads from each account's ModelInfoCache (live data) and falls back
to FALLBACK_MODELS when no cache is populated.
"""

from fastapi import APIRouter, Depends, Request
from loguru import logger

from kiro.config import FALLBACK_MODELS
from kiro.dashboard.deps import require_admin
from kiro.dashboard.schemas import ModelInfo, ModelListResponse
from kiro.db.models import User

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelListResponse)
async def list_models(request: Request, admin: User = Depends(require_admin)):
    """Return all known model IDs from live cache or static fallback."""
    model_ids: dict[str, str] = {}  # id -> source

    try:
        account_manager = getattr(request.app.state, "account_manager", None)
        if account_manager:
            for account in account_manager._accounts.values():
                cache = getattr(account, "model_cache", None)
                if cache and not cache.is_empty():
                    for model_id in cache.list_models():
                        model_ids[model_id] = "cache"
    except Exception as e:
        logger.warning(f"Failed to read model cache from account_manager: {e}")

    if not model_ids:
        for m in FALLBACK_MODELS:
            mid = m.get("modelId", "")
            if mid:
                model_ids[mid] = "fallback"

    models = [ModelInfo(id=mid, source=src) for mid, src in sorted(model_ids.items())]
    return ModelListResponse(models=models, total=len(models))
