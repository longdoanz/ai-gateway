# Google OAuth Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the username/password login form with Google OAuth login while keeping the existing JWT system intact.

**Architecture:** Frontend uses `@react-oauth/google` to get a Google ID token, posts it to a new `POST /api/auth/google` backend endpoint, which verifies the token with Google, auto-provisions the user if new, and returns the same `TokenResponse` as the existing login endpoint.

**Tech Stack:** Python `google-auth` library (backend), `@react-oauth/google` (frontend), Alembic migration (DB), existing FastAPI JWT system unchanged.

---

### Task 1: DB migration — add google_id and email to users

**Files:**
- Create: `alembic/versions/c3d4e5f6a7b8_add_google_auth_to_users.py`
- Modify: `kiro/db/models.py`

- [ ] **Step 1: Add columns to User model**

In `kiro/db/models.py`, add two columns to the `User` class after `is_active`:

```python
google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
email: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

- [ ] **Step 2: Write migration file**

Create `alembic/versions/c3d4e5f6a7b8_add_google_auth_to_users.py`:

```python
"""add google_id and email to users

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('google_id', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    op.create_unique_constraint('uq_users_google_id', 'users', ['google_id'])
    op.create_index('ix_users_google_id', 'users', ['google_id'])


def downgrade() -> None:
    op.drop_index('ix_users_google_id', table_name='users')
    op.drop_constraint('uq_users_google_id', 'users', type_='unique')
    op.drop_column('users', 'email')
    op.drop_column('users', 'google_id')
```

- [ ] **Step 3: Verify tests still pass**

```bash
pytest tests/unit/test_dashboard_schemas.py tests/unit/test_jwt_auth.py -v
```

Expected: all PASS (model change is additive, no existing tests break)

- [ ] **Step 4: Commit**

```bash
git add kiro/db/models.py alembic/versions/c3d4e5f6a7b8_add_google_auth_to_users.py
git commit -m "feat: add google_id and email columns to users table"
```

---

### Task 2: Backend — config, dependency, repository helper, endpoint

**Files:**
- Modify: `kiro/config.py`
- Modify: `requirements.txt`
- Modify: `kiro/db/repositories.py`
- Modify: `kiro/dashboard/routes_auth.py`
- Modify: `kiro/dashboard/schemas.py`
- Create: `tests/unit/test_routes_google_auth.py`

- [ ] **Step 1: Add google-auth to requirements.txt**

In `requirements.txt`, add after `python-multipart>=0.0.9`:

```
google-auth>=2.0.0
```

- [ ] **Step 2: Add config vars to kiro/config.py**

In `kiro/config.py`, add after the `ADMIN_PASSWORD` line (around line 526):

```python
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_ALLOWED_DOMAIN: str = os.getenv("GOOGLE_ALLOWED_DOMAIN", "")
```

- [ ] **Step 3: Add repository helper get_user_by_google_id**

In `kiro/db/repositories.py`, add after `get_user_by_username`:

```python
async def get_user_by_google_id(session: AsyncSession, google_id: str) -> User | None:
    result = await session.execute(select(User).where(User.google_id == google_id))
    return result.scalar_one_or_none()
```

Also update `create_user` to accept optional `google_id` and `email`:

```python
async def create_user(
    session: AsyncSession,
    username: str,
    password: str,
    role: str = "user",
    google_id: str | None = None,
    email: str | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        google_id=google_id,
        email=email,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
```

- [ ] **Step 4: Add GoogleLoginRequest schema**

In `kiro/dashboard/schemas.py`, add after `RefreshRequest`:

```python
class GoogleLoginRequest(BaseModel):
    credential: str
```

- [ ] **Step 5: Write failing tests**

Create `tests/unit/test_routes_google_auth.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from kiro.dashboard.routes_auth import router
from kiro.db.engine import get_session

app = FastAPI()
app.include_router(router)
app.dependency_overrides[get_session] = lambda: AsyncMock()

VALID_PAYLOAD = {
    "sub": "google-uid-123",
    "email": "user@example.com",
    "hd": "example.com",
}


@pytest.mark.asyncio
async def test_google_login_creates_new_user():
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session

    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", "test-client-id"), \
         patch("kiro.dashboard.routes_auth.GOOGLE_ALLOWED_DOMAIN", ""), \
         patch("kiro.dashboard.routes_auth.id_token.verify_oauth2_token", return_value=VALID_PAYLOAD), \
         patch("kiro.dashboard.routes_auth.get_user_by_google_id", new_callable=AsyncMock, return_value=None) as mock_get, \
         patch("kiro.dashboard.routes_auth.create_user", new_callable=AsyncMock) as mock_create, \
         patch("kiro.dashboard.routes_auth.create_access_token", return_value="access-tok"), \
         patch("kiro.dashboard.routes_auth.create_refresh_token", return_value="refresh-tok"):
        mock_create.return_value = MagicMock(id=1, role="user", username="user@example.com")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "access-tok"
    assert data["refresh_token"] == "refresh-tok"
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_google_login_existing_user():
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    existing_user = MagicMock(id=5, role="admin", username="user@example.com", is_active=True)

    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", "test-client-id"), \
         patch("kiro.dashboard.routes_auth.GOOGLE_ALLOWED_DOMAIN", ""), \
         patch("kiro.dashboard.routes_auth.id_token.verify_oauth2_token", return_value=VALID_PAYLOAD), \
         patch("kiro.dashboard.routes_auth.get_user_by_google_id", new_callable=AsyncMock, return_value=existing_user), \
         patch("kiro.dashboard.routes_auth.create_access_token", return_value="access-tok"), \
         patch("kiro.dashboard.routes_auth.create_refresh_token", return_value="refresh-tok"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_google_login_domain_blocked():
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    payload_wrong_domain = {**VALID_PAYLOAD, "hd": "other.com"}

    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", "test-client-id"), \
         patch("kiro.dashboard.routes_auth.GOOGLE_ALLOWED_DOMAIN", "example.com"), \
         patch("kiro.dashboard.routes_auth.id_token.verify_oauth2_token", return_value=payload_wrong_domain):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_google_login_inactive_user():
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    inactive_user = MagicMock(id=2, role="user", username="user@example.com", is_active=False)

    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", "test-client-id"), \
         patch("kiro.dashboard.routes_auth.GOOGLE_ALLOWED_DOMAIN", ""), \
         patch("kiro.dashboard.routes_auth.id_token.verify_oauth2_token", return_value=VALID_PAYLOAD), \
         patch("kiro.dashboard.routes_auth.get_user_by_google_id", new_callable=AsyncMock, return_value=inactive_user):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_google_login_not_configured():
    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", ""):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_google_login_invalid_token():
    from google.auth.exceptions import GoogleAuthError
    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", "test-client-id"), \
         patch("kiro.dashboard.routes_auth.GOOGLE_ALLOWED_DOMAIN", ""), \
         patch("kiro.dashboard.routes_auth.id_token.verify_oauth2_token", side_effect=GoogleAuthError("bad")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 401
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
pip install google-auth -q && pytest tests/unit/test_routes_google_auth.py -v
```

Expected: FAIL with `ImportError` or `404` (endpoint not yet implemented)

- [ ] **Step 7: Implement /auth/google endpoint**

In `kiro/dashboard/routes_auth.py`, add imports at top:

```python
import secrets
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google.auth.exceptions import GoogleAuthError
from kiro.config import GOOGLE_CLIENT_ID, GOOGLE_ALLOWED_DOMAIN
from kiro.db.repositories import get_user_by_google_id, create_user
from kiro.dashboard.schemas import GoogleLoginRequest
```

Then add the endpoint after the `refresh` route:

```python
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
        access_token=create_access_token(user.id, user.role, user.username),
        refresh_token=create_refresh_token(user.id),
    )
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
pytest tests/unit/test_routes_google_auth.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 9: Run full test suite to check for regressions**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: all PASS

- [ ] **Step 10: Commit**

```bash
git add requirements.txt kiro/config.py kiro/db/repositories.py kiro/dashboard/schemas.py kiro/dashboard/routes_auth.py tests/unit/test_routes_google_auth.py
git commit -m "feat: add Google OAuth login endpoint with auto-provisioning"
```

---

### Task 3: Frontend — Google OAuth login UI

**Files:**
- Modify: `webui/lib/auth.tsx`
- Modify: `webui/lib/providers.tsx`
- Modify: `webui/app/(auth)/login/page.tsx`
- Modify: `webui/lib/types.ts`

- [ ] **Step 1: Install @react-oauth/google**

```bash
cd webui && npm install @react-oauth/google
```

Expected: package added to `node_modules` and `package.json`

- [ ] **Step 2: Add GoogleLoginRequest type to types.ts**

In `webui/lib/types.ts`, add after `RefreshRequest`:

```ts
export interface GoogleLoginRequest {
  credential: string;
}
```

- [ ] **Step 3: Update AuthContextValue and AuthProvider in auth.tsx**

Replace the full content of `webui/lib/auth.tsx` with:

```tsx
"use client";

import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import type { JwtPayload, LoginRequest, TokenResponse } from "@/lib/types";
import apiClient, { clearTokens, getStoredRefreshToken, setTokens } from "@/lib/api-client";

export interface AuthUser {
  id: number;
  role: "admin" | "user";
  username: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  loginWithGoogle: (credential: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  login: async () => {},
  loginWithGoogle: async () => {},
  logout: () => {},
});

function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const base64 = token.split(".")[1];
    const json = atob(base64.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function userFromToken(token: string): AuthUser | null {
  const payload = decodeJwtPayload(token);
  if (!payload || payload.type !== "access") return null;
  if (payload.exp * 1000 < Date.now()) return null;
  return { id: parseInt(payload.sub), role: payload.role, username: payload.username || "" };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const rt = getStoredRefreshToken();
    if (!rt) {
      setIsLoading(false);
      return;
    }
    apiClient
      .post<TokenResponse>("/auth/refresh", { refresh_token: rt })
      .then((res) => {
        setTokens(res.data.access_token, res.data.refresh_token);
        setUser(userFromToken(res.data.access_token));
      })
      .catch(() => {
        clearTokens();
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (credentials: LoginRequest) => {
    const res = await apiClient.post<TokenResponse>("/auth/login", credentials);
    setTokens(res.data.access_token, res.data.refresh_token);
    setUser(userFromToken(res.data.access_token));
  }, []);

  const loginWithGoogle = useCallback(async (credential: string) => {
    const res = await apiClient.post<TokenResponse>("/auth/google", { credential });
    setTokens(res.data.access_token, res.data.refresh_token);
    setUser(userFromToken(res.data.access_token));
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, login, loginWithGoogle, logout }),
    [user, isLoading, login, loginWithGoogle, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
```

- [ ] **Step 4: Wrap providers with GoogleOAuthProvider**

Replace the full content of `webui/lib/providers.tsx` with:

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { AuthProvider } from "@/lib/auth";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
          },
        },
      })
  );

  return (
    <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID!}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    </GoogleOAuthProvider>
  );
}
```

- [ ] **Step 5: Replace login page with Google button**

Replace the full content of `webui/app/(auth)/login/page.tsx` with:

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { GoogleLogin } from "@react-oauth/google";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const { loginWithGoogle } = useAuth();
  const [error, setError] = useState("");

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="glass-panel-elevated rounded-3xl p-10 shadow-[0_8px_40px_rgba(79,70,229,0.10)]">
          <div className="text-center mb-8">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary-container to-primary flex items-center justify-center text-white font-bold text-lg shadow-[0_4px_16px_rgba(79,70,229,0.3)] mx-auto mb-4">
              AI
            </div>
            <h1 className="text-2xl font-bold text-on-surface tracking-tight">AI Gateway</h1>
            <p className="text-on-surface-variant text-sm mt-1">Sign in to your dashboard</p>
          </div>
          <div className="flex flex-col items-center gap-4">
            <GoogleLogin
              onSuccess={async (response) => {
                try {
                  setError("");
                  await loginWithGoogle(response.credential!);
                  router.push("/");
                } catch {
                  setError("Login failed. Please try again.");
                }
              }}
              onError={() => setError("Google sign-in failed. Please try again.")}
              width="100%"
              theme="outline"
              size="large"
              text="signin_with"
            />
            {error && (
              <div className="flex items-center gap-2 text-sm text-error bg-error/5 border border-error/20 rounded-xl px-3 py-2 w-full">
                <span className="material-symbols-outlined text-[16px]">error</span>
                {error}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Add env var to .env.local**

Check if `webui/.env.local` exists; if not create it. Add:

```
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

(Replace with real Client ID from Google Cloud Console)

- [ ] **Step 7: Commit**

```bash
cd webui && git add package.json package-lock.json lib/auth.tsx lib/providers.tsx lib/types.ts "app/(auth)/login/page.tsx" && cd .. && git commit -m "feat: replace login form with Google OAuth button"
```

---

## Notes

- **E2E tests:** `tests/e2e/global-setup.ts` uses username/password login. Since `/auth/login` backend is preserved, keep a test user with password for Playwright — no changes needed to E2E setup.
- **Existing admin access:** `/auth/login` still works via backend; no UI entry point but accessible via API for emergency admin access.
- **Google Cloud Console:** Before running, create OAuth 2.0 Client ID, add `http://localhost:3000` as authorized JS origin, set `NEXT_PUBLIC_GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_ID` in respective env files.
