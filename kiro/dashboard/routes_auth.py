import secrets
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google.auth.exceptions import GoogleAuthError

from kiro.config import GOOGLE_CLIENT_ID, GOOGLE_ALLOWED_DOMAIN
from kiro.dashboard.jwt_auth import create_access_token, create_refresh_token, decode_token
from kiro.dashboard.schemas import GoogleLoginRequest, LoginRequest, RefreshRequest, TokenResponse
from kiro.db.engine import get_session
from kiro.db.repositories import create_user, get_user_by_email, get_user_by_google_id, get_user_by_id, get_user_by_username, update_user, verify_password

_login_attempts: dict[str, list[float]] = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # 5 minutes


def _check_rate_limit(key: str) -> None:
    now = time.time()
    attempts = _login_attempts[key]
    # Remove old attempts outside the window
    _login_attempts[key] = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
    if len(_login_attempts[key]) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {LOGIN_WINDOW_SECONDS // 60} minutes.",
        )
    _login_attempts[key].append(now)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(f"ip:{client_ip}")
    _check_rate_limit(f"user:{body.username}")
    user = await get_user_by_username(session, body.username)
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.username, user.can_create_gateway_key),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = await get_user_by_id(session, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.username, user.can_create_gateway_key),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/google", response_model=TokenResponse)
async def google_login(body: GoogleLoginRequest, session: AsyncSession = Depends(get_session)):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google OAuth not configured")
    try:
        payload = id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except (GoogleAuthError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

    if GOOGLE_ALLOWED_DOMAIN:
        hd = payload.get("hd", "")
        if hd != GOOGLE_ALLOWED_DOMAIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access restricted to @{GOOGLE_ALLOWED_DOMAIN} accounts",
            )

    google_id = payload["sub"]
    email = payload.get("email", "")

    user = await get_user_by_google_id(session, google_id)
    if user is None:
        # Check if a pre-provisioned account exists for this email
        user = await get_user_by_email(session, email)
        if user is not None:
            # Link the Google ID to the existing pre-provisioned account
            if not user.is_active:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is disabled")
            await update_user(session, user.id, google_id=google_id, username=email if user.username == email else user.username)
            user = await get_user_by_google_id(session, google_id)
        else:
            user = await create_user(
                session,
                username=email,
                password=secrets.token_hex(32),
                role="user",
                google_id=google_id,
                email=email,
            )
    elif not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is disabled")

    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.username, user.can_create_gateway_key),
        refresh_token=create_refresh_token(user.id),
    )
