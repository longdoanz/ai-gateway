import csv
import io
import json

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kiro.dashboard.deps import require_admin
from kiro.dashboard.schemas import ImportResult, KiroUserMappingResponse, PaginationParams
from kiro.db.engine import get_session
from kiro.db.models import KiroUserMapping, User
from kiro.db.repositories import upsert_kiro_user_mappings, list_kiro_user_mappings

router = APIRouter(prefix="/import", tags=["import"])

REQUIRED_FIELDS = {"kiro_user_id"}
OPTIONAL_FIELDS = {"email", "username"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


@router.get("/kiro-users", response_model=list[KiroUserMappingResponse])
async def get_kiro_users(
    params: PaginationParams = Depends(),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await list_kiro_user_mappings(session, limit=params.limit, offset=params.offset)


@router.post("/users", response_model=ImportResult)
async def import_users(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large (max 5MB)")

    content = await file.read()
    text = content.decode("utf-8-sig")
    errors: list[str] = []
    mappings: list[dict] = []

    filename = file.filename or ""
    if filename.endswith(".json"):
        try:
            data = json.loads(text)
            if not isinstance(data, list):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON must be an array of objects")
            for i, row in enumerate(data):
                if "kiro_user_id" not in row:
                    errors.append(f"Row {i}: missing kiro_user_id")
                    continue
                mappings.append({"kiro_user_id": row["kiro_user_id"], "email": row.get("email"), "username": row.get("username")})
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON: {e}")
    else:
        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader):
            if "kiro_user_id" not in row or not row["kiro_user_id"]:
                errors.append(f"Row {i + 1}: missing kiro_user_id")
                continue
            mappings.append({"kiro_user_id": row["kiro_user_id"], "email": row.get("email"), "username": row.get("username")})

    if not mappings:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid mappings found in file")

    inserted, updated = await upsert_kiro_user_mappings(session, mappings)
    return ImportResult(imported=inserted, updated=updated, errors=errors)


@router.patch("/kiro-users/{kiro_user_id}", response_model=KiroUserMappingResponse)
async def toggle_kiro_user(
    kiro_user_id: str,
    is_active: bool = Body(..., embed=True),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(KiroUserMapping).where(KiroUserMapping.kiro_user_id == kiro_user_id))
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kiro user not found")
    mapping.is_active = is_active
    await session.commit()
    await session.refresh(mapping)
    return mapping
