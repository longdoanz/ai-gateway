from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from kiro.config import JWT_SECRET, JWT_ACCESS_EXPIRY, JWT_REFRESH_EXPIRY

ALGORITHM = "HS256"


def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(seconds=JWT_ACCESS_EXPIRY)
    payload = {"sub": str(user_id), "role": role, "exp": expire, "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(seconds=JWT_REFRESH_EXPIRY)
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
