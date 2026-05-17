from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from kiro.dashboard.deps import require_admin
from kiro.dashboard.schemas import ApiKeyResponse, SystemKeyCreate, SystemKeyUpdate
from kiro.db.engine import get_session
from kiro.db.models import ApiKey
from kiro.db.repositories import (
    create_api_key,
    get_api_key_by_hash,
    hash_api_key,
    update_api_key,
)

router = APIRouter(prefix="/system-keys", tags=["system-keys"])


@router.get("", response_model=list[ApiKeyResponse])
async def get_system_keys(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ApiKey).where(ApiKey.is_system == True).order_by(ApiKey.id).limit(limit).offset(offset)
    result = await session.execute(stmt)
    keys = result.scalars().all()
    return [ApiKeyResponse.model_validate(k) for k in keys]


@router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def register_system_key(
    body: SystemKeyCreate,
    _=Depends(require_admin),
    session: AsyncSession = Depends(get_session)
):
    existing = await get_api_key_by_hash(session, hash_api_key(body.raw_key))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This API key is already registered")
    
    return await create_api_key(
        session, 
        user_id=None, 
        raw_key=body.raw_key, 
        is_system=True, 
        use_proxy=body.use_proxy
    )


@router.put("/{key_id}", response_model=ApiKeyResponse)
async def update_system_key(
    key_id: int, 
    body: SystemKeyUpdate, 
    _=Depends(require_admin), 
    session: AsyncSession = Depends(get_session)
):
    stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.is_system == True)
    result = await session.execute(stmt)
    key = result.scalar_one_or_none()
    
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System key not found")
    
    update_data = {}
    if body.is_active is not None:
        update_data["is_active"] = body.is_active
    if body.use_proxy is not None:
        update_data["use_proxy"] = body.use_proxy
        
    if update_data:
        await update_api_key(session, key_id, **update_data)
        
        # Update cache
        try:
            from kiro.usage.usage_cache import usage_cache
            entry = usage_cache.get(key_id)
            if entry:
                if body.is_active is not None:
                    entry.is_active = body.is_active
                if body.use_proxy is not None:
                    entry.use_proxy = body.use_proxy
        except Exception:
            pass
            
    # Refresh key object
    await session.refresh(key)
    return ApiKeyResponse.model_validate(key)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_key(
    key_id: int, 
    _=Depends(require_admin), 
    session: AsyncSession = Depends(get_session)
):
    from sqlalchemy import delete
    from kiro.db.models import KeyUsage, DailyUsage, FallbackUsage
    
    stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.is_system == True)
    result = await session.execute(stmt)
    key = result.scalar_one_or_none()
    
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System key not found")
    
    # Delete related usage data first to avoid foreign key constraints
    await session.execute(delete(KeyUsage).where(KeyUsage.key_id == key_id))
    await session.execute(delete(DailyUsage).where(DailyUsage.key_id == key_id))
    await session.execute(delete(FallbackUsage).where(
        (FallbackUsage.original_key_id == key_id) | (FallbackUsage.fallback_key_id == key_id)
    ))
    
    # Delete the key itself
    await session.execute(delete(ApiKey).where(ApiKey.id == key_id))
    await session.commit()
    
    try:
        from kiro.usage.usage_cache import usage_cache
        usage_cache.remove_key(key_id)
    except Exception:
        pass
