"""
Dashboard endpoints: manage Service Accounts.

A Service Account is a non-human identity (a CI bot, an app, a team) that is
explicitly NOT tied to a User (unlike GatewayKey, which is 1:1 with a User).
Each service account holds one or more API keys and an admin-configured
allowlist of models. Its traffic is always forwarded straight to 9router,
never the Kiro pool — request-path enforcement of that lives elsewhere; this
module only manages the data layer (CRUD + key issuance + usage reporting).

All endpoints here are admin-only.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import require_admin
from kiro.dashboard.schemas import (
    ServiceAccountCreate,
    ServiceAccountKeyCreated,
    ServiceAccountKeyResponse,
    ServiceAccountResponse,
    ServiceAccountUpdate,
    ServiceAccountUsageHistoryResponse,
)
from kiro.db.engine import get_session
from kiro.db.models import ServiceAccount, User
from kiro.db.repositories import (
    create_service_account,
    create_service_account_key,
    decode_allowed_models,
    delete_service_account,
    get_service_account_by_id,
    get_service_account_by_name,
    get_service_account_daily_usage,
    get_service_account_usage_history,
    list_service_account_keys,
    list_service_accounts,
    revoke_service_account_key,
    update_service_account,
)

router = APIRouter(prefix="/service-accounts", tags=["service-accounts"])


def _to_response(service_account: ServiceAccount) -> ServiceAccountResponse:
    """Build the API response for a ServiceAccount.

    Decodes the stored allowed_models JSON and derives key_count from the
    (selectin-loaded) keys relationship.

    Args:
        service_account: The ORM instance to serialize.

    Returns:
        A populated ServiceAccountResponse.
    """
    models = decode_allowed_models(service_account.allowed_models)
    return ServiceAccountResponse(
        id=service_account.id,
        name=service_account.name,
        description=service_account.description,
        is_active=service_account.is_active,
        allowed_models=models,
        allowed_model_count=len(models),
        key_count=len(service_account.keys),
        created_by_user_id=service_account.created_by_user_id,
        created_at=service_account.created_at,
    )


@router.get("", response_model=list[ServiceAccountResponse])
async def get_service_accounts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """List service accounts, including key count and allowed-model count."""
    accounts = await list_service_accounts(session, limit=limit, offset=offset)
    return [_to_response(a) for a in accounts]


@router.post("", response_model=ServiceAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_service_account_endpoint(
    body: ServiceAccountCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Create a new service account."""
    existing = await get_service_account_by_name(session, body.name)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A service account with this name already exists")
    service_account = await create_service_account(
        session,
        name=body.name,
        description=body.description,
        allowed_models=body.allowed_models,
        created_by_user_id=admin.id,
    )
    return _to_response(service_account)


@router.patch("/{service_account_id}", response_model=ServiceAccountResponse)
async def update_service_account_endpoint(
    service_account_id: int,
    body: ServiceAccountUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Update a service account's name, description, allowed_models, and/or is_active."""
    existing = await get_service_account_by_id(session, service_account_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service account not found")

    updates = body.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] != existing.name:
        name_conflict = await get_service_account_by_name(session, updates["name"])
        if name_conflict:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A service account with this name already exists")

    updated = await update_service_account(session, service_account_id, **updates)
    return _to_response(updated)


@router.delete("/{service_account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_account_endpoint(
    service_account_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Soft-delete a service account: deactivate it and all of its keys."""
    deleted = await delete_service_account(session, service_account_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service account not found")


@router.get("/{service_account_id}/keys", response_model=list[ServiceAccountKeyResponse])
async def get_service_account_keys(
    service_account_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """List a service account's keys, masked to prefix + suffix only."""
    existing = await get_service_account_by_id(session, service_account_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service account not found")
    return await list_service_account_keys(session, service_account_id)


@router.post("/{service_account_id}/keys", response_model=ServiceAccountKeyCreated, status_code=status.HTTP_201_CREATED)
async def issue_service_account_key(
    service_account_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Issue a new API key for a service account.

    The raw key is returned exactly once in this response — it is never
    recoverable afterward (only its salted hash is stored).
    """
    existing = await get_service_account_by_id(session, service_account_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service account not found")
    key, raw_key = await create_service_account_key(session, service_account_id)
    return ServiceAccountKeyCreated(
        id=key.id,
        service_account_id=key.service_account_id,
        key_prefix=key.key_prefix,
        key_suffix=key.key_suffix,
        is_active=key.is_active,
        created_at=key.created_at,
        raw_key=raw_key,
    )


@router.delete("/{service_account_id}/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_service_account_key_endpoint(
    service_account_id: int,
    key_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Revoke one of a service account's keys."""
    revoked = await revoke_service_account_key(session, service_account_id, key_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")


@router.get("/{service_account_id}/usage", response_model=ServiceAccountUsageHistoryResponse)
async def get_service_account_usage(
    service_account_id: int,
    days: int = Query(default=30, ge=1, le=365),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Return monthly usage rollup and a recent daily breakdown for a service account."""
    existing = await get_service_account_by_id(session, service_account_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service account not found")
    monthly = await get_service_account_usage_history(session, service_account_id)
    daily = await get_service_account_daily_usage(session, service_account_id, limit=days)
    return ServiceAccountUsageHistoryResponse(monthly=monthly, daily=daily)
