from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import require_admin, get_current_user
from kiro.dashboard.schemas import UserCreate, UserDetailResponse, UserResponse, UserUpdate
from kiro.db.engine import get_session
from kiro.db.models import User
from kiro.db.repositories import create_user, get_user_by_id, get_user_by_username, list_users, update_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def get_users(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return await list_users(session)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_new_user(body: UserCreate, admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    existing = await get_user_by_username(session, body.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    return await create_user(session, body.username, body.password, body.role)


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user(user_id: int, caller: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if caller.role != "admin" and caller.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_existing_user(user_id: int, body: UserUpdate, admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    user = await update_user(session, user_id, **updates)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
