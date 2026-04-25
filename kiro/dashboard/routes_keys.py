from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user, require_admin
from kiro.dashboard.schemas import ApiKeyCreate, ApiKeyResponse, ApiKeyToggle, KeyUsageResponse
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import (
    create_api_key,
    get_api_key_by_hash,
    get_all_usage_for_month,
    get_usage_for_month,
    hash_api_key,
    list_api_keys,
    update_api_key,
)

router = APIRouter(prefix="/keys", tags=["keys"])


@router.get("", response_model=list[ApiKeyResponse])
async def get_keys(caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    user_id = None if caller.role == "admin" else caller.id
    return await list_api_keys(session, user_id=user_id)


@router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def register_key(body: ApiKeyCreate, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    existing = await get_api_key_by_hash(session, hash_api_key(body.raw_key))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This API key is already registered")
    return await create_api_key(session, caller.id, body.raw_key)


@router.put("/{key_id}", response_model=ApiKeyResponse)
async def toggle_key(key_id: int, body: ApiKeyToggle, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    keys = await list_api_keys(session, user_id=None if caller.role == "admin" else caller.id)
    key = next((k for k in keys if k.id == key_id), None)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    await update_api_key(session, key_id, is_active=body.is_active)
    key.is_active = body.is_active
    return key


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_key(key_id: int, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    keys = await list_api_keys(session, user_id=None if caller.role == "admin" else caller.id)
    key = next((k for k in keys if k.id == key_id), None)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    await update_api_key(session, key_id, is_active=False)


@router.get("/{key_id}/usage", response_model=list[KeyUsageResponse])
async def get_key_usage(key_id: int, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    keys = await list_api_keys(session, user_id=None if caller.role == "admin" else caller.id)
    key = next((k for k in keys if k.id == key_id), None)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    from sqlalchemy import select
    from kiro.db.models import KeyUsage
    result = await session.execute(select(KeyUsage).where(KeyUsage.key_id == key_id).order_by(KeyUsage.month.desc()))
    return list(result.scalars().all())
