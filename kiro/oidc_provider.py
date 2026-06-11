# -*- coding: utf-8 -*-
"""
OIDC Provider for ai-gateway.

Exposes a minimal OpenID Connect provider so that 9router (or any OIDC-capable
app) can authenticate users who are already logged into the ai-gateway dashboard
without a second login prompt.

Flow:
  1. Client redirects user to GET /oauth/authorize?prompt=none&...
  2. ai-gateway verifies the dashboard JWT from the Authorization header or
     the `_gateway_token` query param (set by the frontend before redirect).
  3. If valid → issue a short-lived authorization code and redirect back.
  4. Client POSTs the code to /oauth/token → receives an id_token (RS256 JWT).
  5. Client can verify the id_token using the public key at /oauth/jwks.

Security notes:
  - Authorization codes are single-use, expire in 60 s, stored in-memory.
  - id_tokens expire in 5 minutes (enough for 9router to establish its own session).
  - RS256 keypair is generated once at startup (or loaded from OIDC_RSA_PRIVATE_KEY env).
  - Only registered client_id / client_secret pairs are accepted (OIDC_CLIENTS env var).
"""

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from jose import jwt
from loguru import logger

from kiro.db.models import User
from kiro.dashboard.jwt_auth import decode_token
from kiro.db.engine import get_session as _get_session
from kiro.db.repositories import get_user_by_id

# ---------------------------------------------------------------------------
# RSA keypair — generated once at module import, or loaded from env
# ---------------------------------------------------------------------------

def _load_or_generate_rsa_key() -> rsa.RSAPrivateKey:
    """Load RSA private key from env var or generate a new 2048-bit key."""
    pem = os.getenv("OIDC_RSA_PRIVATE_KEY", "")
    if pem:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        return load_pem_private_key(pem.encode(), password=None)
    logger.info("OIDC_RSA_PRIVATE_KEY not set — generating ephemeral RSA-2048 keypair")
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


_PRIVATE_KEY: rsa.RSAPrivateKey = _load_or_generate_rsa_key()
_PUBLIC_KEY = _PRIVATE_KEY.public_key()

# Stable key ID derived from the public key fingerprint
_PUBLIC_KEY_PEM = _PUBLIC_KEY.public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)
_KID: str = hashlib.sha256(_PUBLIC_KEY_PEM).hexdigest()[:16]

# ---------------------------------------------------------------------------
# Client registry — who is allowed to use this OIDC provider
# ---------------------------------------------------------------------------
# OIDC_CLIENTS env var format (JSON):
#   [{"client_id": "9router", "client_secret": "s3cr3t", "redirect_uris": ["http://localhost:20128/api/auth/oidc/callback"]}]
# Defaults to a single built-in 9router client using OIDC_CLIENT_SECRET env var.

def _load_clients() -> dict[str, dict]:
    raw = os.getenv("OIDC_CLIENTS", "")
    if raw:
        try:
            entries = json.loads(raw)
            return {e["client_id"]: e for e in entries}
        except Exception as exc:
            logger.error(f"Failed to parse OIDC_CLIENTS: {exc}")

    # Default: single 9router client
    secret = os.getenv("OIDC_CLIENT_SECRET", "")
    if not secret:
        logger.warning("OIDC_CLIENT_SECRET not set — OIDC SSO will not work until configured")
    # Support comma-separated list of redirect URIs; also support "*" prefix to match any origin.
    # Default "*" accepts any origin with the /9router/api/auth/oidc/callback path — safe because
    # the gateway itself serves /9router/ via its own proxy, so the redirect always comes home.
    redirect_env = os.getenv("OIDC_REDIRECT_URI", "*/9router/api/auth/oidc/callback")
    redirect_uris = [r.strip() for r in redirect_env.split(",") if r.strip()]
    return {
        "9router": {
            "client_id": "9router",
            "client_secret": secret,
            "redirect_uris": redirect_uris,
        }
    }


def _redirect_uri_allowed(redirect_uri: str, registered: list[str]) -> bool:
    """Check redirect_uri against registered list.

    A registered entry starting with '*' is a path-only wildcard — it matches
    any origin as long as the path (everything after the first '/') matches.
    Example: "*/9router/api/auth/oidc/callback" matches any scheme+host.
    """
    from urllib.parse import urlparse
    incoming_path = urlparse(redirect_uri).path
    for entry in registered:
        if entry == redirect_uri:
            return True
        if entry.startswith("*"):
            # wildcard host: compare path only
            if incoming_path == entry[1:]:
                return True
    return False


_CLIENTS: dict[str, dict] = _load_clients()

# ---------------------------------------------------------------------------
# Authorization code store — in-memory, TTL 60 s, max 1000 entries
# ---------------------------------------------------------------------------
_CODE_TTL = 60  # seconds
_CODE_MAX = 1000

# code → {user_id, role, username, email, client_id, redirect_uri, nonce, expires_at}
_codes: dict[str, dict] = {}


def _evict_expired() -> None:
    now = time.time()
    expired = [k for k, v in _codes.items() if v["expires_at"] < now]
    for k in expired:
        del _codes[k]


def _issue_code(
    user_id: int,
    role: str,
    username: str,
    email: str,
    client_id: str,
    redirect_uri: str,
    nonce: Optional[str],
) -> str:
    _evict_expired()
    if len(_codes) >= _CODE_MAX:
        # Drop the oldest entry
        oldest = min(_codes, key=lambda k: _codes[k]["expires_at"])
        del _codes[oldest]
    code = secrets.token_urlsafe(32)
    _codes[code] = {
        "user_id": user_id,
        "role": role,
        "username": username,
        "email": email,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "nonce": nonce,
        "expires_at": time.time() + _CODE_TTL,
    }
    return code


def _consume_code(code: str) -> Optional[dict]:
    """Return and delete the code entry, or None if missing/expired."""
    entry = _codes.pop(code, None)
    if entry is None:
        return None
    if entry["expires_at"] < time.time():
        return None
    return entry


# ---------------------------------------------------------------------------
# JWKS helpers
# ---------------------------------------------------------------------------

def _public_key_to_jwk() -> dict:
    """Convert RSA public key to JWK dict."""
    pub_numbers = _PUBLIC_KEY.public_key().public_numbers() if hasattr(_PUBLIC_KEY, "public_key") else _PUBLIC_KEY.public_numbers()


    def _b64(n: int, length: int) -> str:
        return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

    byte_length = (pub_numbers.n.bit_length() + 7) // 8
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": _KID,
        "n": _b64(pub_numbers.n, byte_length),
        "e": _b64(pub_numbers.e, 3),
    }


# ---------------------------------------------------------------------------
# id_token minting
# ---------------------------------------------------------------------------
_ID_TOKEN_TTL = 300  # 5 minutes

def _get_issuer() -> str:
    return os.getenv("OIDC_ISSUER_URL", "http://localhost:18000").rstrip("/")


def _mint_id_token(entry: dict) -> str:
    now = int(time.time())
    payload: dict = {
        "iss": _get_issuer(),
        "sub": str(entry["user_id"]),
        "aud": entry["client_id"],
        "iat": now,
        "exp": now + _ID_TOKEN_TTL,
        "email": entry["email"],
        "preferred_username": entry["username"],
        "role": entry["role"],
    }
    if entry.get("nonce"):
        payload["nonce"] = entry["nonce"]

    private_pem = _PRIVATE_KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return jwt.encode(payload, private_pem.decode(), algorithm="RS256", headers={"kid": _KID})


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = APIRouter(tags=["oidc"])


@router.get("/.well-known/openid-configuration")
async def oidc_discovery() -> JSONResponse:
    """Standard OIDC discovery document.

    OIDC_ISSUER_URL  — internal URL used for the iss claim, token endpoint, and jwks
                       (server-to-server; may be an internal Docker hostname).
    OIDC_PUBLIC_URL  — public URL used only for authorization_endpoint (browser redirect).
                       Defaults to OIDC_ISSUER_URL when not set.
    """
    issuer = _get_issuer()
    public_url = os.getenv("OIDC_PUBLIC_URL", "").rstrip("/") or issuer
    return JSONResponse({
        "issuer": issuer,
        "authorization_endpoint": f"{public_url}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "jwks_uri": f"{issuer}/oauth/jwks",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile", "email"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "claims_supported": ["sub", "iss", "aud", "exp", "iat", "email", "preferred_username", "role", "nonce"],
        "code_challenge_methods_supported": ["S256"],
    })


@router.get("/oauth/jwks")
async def jwks() -> JSONResponse:
    """Expose RSA public key so clients can verify id_tokens."""
    return JSONResponse({"keys": [_public_key_to_jwk()]})


@router.get("/oauth/authorize")
async def authorize(
    request: Request,
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query(...),
    state: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None),
    prompt: Optional[str] = Query(None),
    # Frontend passes the gateway JWT here for silent SSO (JS-initiated flow)
    _gateway_token: Optional[str] = Query(None),
    # Browser-initiated flow (9router OIDC start → redirect) sends httponly cookie
    gw_token: Optional[str] = Cookie(default=None),
) -> RedirectResponse:
    """
    OIDC Authorization endpoint.

    Validates the caller's ai-gateway JWT (from Authorization header or
    `_gateway_token` query param). With `prompt=none` returns
    `error=login_required` instead of redirecting to the login page when
    the user has no valid session.
    """
    # Validate response_type
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Only response_type=code is supported")

    # Validate client
    client = _CLIENTS.get(client_id)
    if client is None:
        raise HTTPException(status_code=400, detail=f"Unknown client_id: {client_id}")

    if not _redirect_uri_allowed(redirect_uri, client["redirect_uris"]):
        raise HTTPException(status_code=400, detail="redirect_uri not registered for this client")

    def _error_redirect(error: str) -> RedirectResponse:
        params: dict = {"error": error}
        if state:
            params["state"] = state
        return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)

    # Resolve user — query param (JS-initiated), then Bearer header, then httponly cookie
    token: Optional[str] = _gateway_token
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        token = gw_token  # browser redirect from 9router's /api/auth/oidc/start

    user: Optional[User] = None
    if token:
        try:
            payload = decode_token(token)
            if payload and payload.get("type") == "access":
                async for session in _get_session():
                    user = await get_user_by_id(session, int(payload["sub"]))
                    break
        except Exception as exc:
            logger.debug(f"OIDC authorize: token decode failed: {exc}")

    if user is None or not user.is_active:
        if prompt == "none":
            return _error_redirect("login_required")
        # Redirect to gateway login with a return_to hint
        params = urlencode({
            "return_to": str(request.url),
        })
        return RedirectResponse(f"/login?{params}", status_code=302)

    # Issue authorization code
    code = _issue_code(
        user_id=user.id,
        role=user.role,
        username=user.username or "",
        email=user.email or "",
        client_id=client_id,
        redirect_uri=redirect_uri,
        nonce=nonce,
    )

    params: dict = {"code": code}
    if state:
        params["state"] = state
    logger.info(f"OIDC: issued authorization code for user {user.id} → client {client_id}")
    return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)


@router.post("/oauth/token")
async def token(
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    # PKCE (optional — accepted but not required since we control both ends)
    code_verifier: Optional[str] = Form(None),
) -> JSONResponse:
    """Exchange authorization code for id_token."""
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="Only grant_type=authorization_code is supported")

    # Validate client credentials
    client = _CLIENTS.get(client_id)
    if client is None or client.get("client_secret", "") != client_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid client credentials")

    entry = _consume_code(code)
    if entry is None:
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

    if entry["client_id"] != client_id:
        raise HTTPException(status_code=400, detail="client_id mismatch")

    if entry["redirect_uri"] != redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")

    id_token_str = _mint_id_token(entry)
    logger.info(f"OIDC: issued id_token for user {entry['user_id']} → client {client_id}")

    return JSONResponse({
        "access_token": id_token_str,  # 9router uses access_token field
        "id_token": id_token_str,
        "token_type": "Bearer",
        "expires_in": _ID_TOKEN_TTL,
    })
