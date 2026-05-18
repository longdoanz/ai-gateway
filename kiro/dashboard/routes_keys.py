from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user, require_admin
from kiro.dashboard.schemas import ApiKeyCreate, ApiKeyResponse, ApiKeyToggle, KeyUsageResponse
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import (
    build_kiro_email_lookup,
    create_api_key,
    delete_api_key,
    get_api_key_by_hash,
    get_all_usage_for_month,
    get_usage_history,
    get_usage_for_month,
    hash_api_key,
    list_api_keys,
    resolve_kiro_email,
    update_api_key,
)

router = APIRouter(prefix="/keys", tags=["keys"])


@router.get("", response_model=list[ApiKeyResponse])
async def get_keys(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = None if caller.role == "admin" else caller.id
    keys = await list_api_keys(session, user_id=user_id, limit=limit, offset=offset)
    lookup = await build_kiro_email_lookup(session)
    results = []
    for k in keys:
        resp = ApiKeyResponse.model_validate(k)
        if k.kiro_user_id:
            resp.kiro_email = resolve_kiro_email(k.kiro_user_id, lookup)
        results.append(resp)
    return results


@router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def register_key(body: ApiKeyCreate, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    existing = await get_api_key_by_hash(session, hash_api_key(body.raw_key))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This API key is already registered")
    target_user_id = caller.id
    if caller.role == "admin" and body.user_id is not None:
        from kiro.db.repositories import get_user_by_id
        target = await get_user_by_id(session, body.user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found")
        target_user_id = body.user_id
    return await create_api_key(session, target_user_id, body.raw_key)


@router.put("/{key_id}", response_model=ApiKeyResponse)
async def toggle_key(key_id: int, body: ApiKeyToggle, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    keys = await list_api_keys(session, user_id=None if caller.role == "admin" else caller.id)
    key = next((k for k in keys if k.id == key_id), None)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    await update_api_key(session, key_id, is_active=body.is_active)
    try:
        from kiro.usage.usage_cache import usage_cache
        usage_cache.set_key_active(key_id, body.is_active)
    except Exception:
        pass
    key.is_active = body.is_active
    return key


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(key_id: int, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    keys = await list_api_keys(session, user_id=None if caller.role == "admin" else caller.id)
    key = next((k for k in keys if k.id == key_id), None)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")

    await delete_api_key(session, key_id)


@router.get("/{key_id}/usage", response_model=list[KeyUsageResponse])
async def get_key_usage(key_id: int, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    keys = await list_api_keys(session, user_id=None if caller.role == "admin" else caller.id)
    key = next((k for k in keys if k.id == key_id), None)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return await get_usage_history(session, key_id)
