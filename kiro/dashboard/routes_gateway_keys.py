from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import get_current_user
from kiro.dashboard.schemas import GatewayKeyCreated, GatewayKeyResponse
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import (
    create_gateway_key,
    delete_gateway_key,
    get_gateway_key_by_user_id,
)

router = APIRouter(prefix="/gateway-keys", tags=["gateway-keys"])


@router.get("/me", response_model=GatewayKeyResponse | None)
async def get_my_gateway_key(
    caller: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await get_gateway_key_by_user_id(session, caller.id)


@router.post("/me", response_model=GatewayKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_my_gateway_key(
    caller: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not caller.can_create_gateway_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to create gateway key")
    existing = await get_gateway_key_by_user_id(session, caller.id)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Gateway key already exists. Revoke it first.")
    gk, raw_key = await create_gateway_key(session, caller.id)
    return GatewayKeyCreated(
        id=gk.id,
        user_id=gk.user_id,
        key_prefix=gk.key_prefix,
        key_suffix=gk.key_suffix,
        is_active=gk.is_active,
        created_at=gk.created_at,
        raw_key=raw_key,
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_gateway_key(
    caller: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    deleted = await delete_gateway_key(session, caller.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No gateway key found")
