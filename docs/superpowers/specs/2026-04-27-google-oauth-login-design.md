# Google OAuth Login Design

**Date:** 2026-04-27  
**Status:** Approved  
**Approach:** Frontend-driven (Google Identity Services JS — Option A)

## Overview

Replace the username/password login form with Google OAuth login. The backend JWT system remains unchanged; only a new `/auth/google` endpoint is added. Users who sign in with Google for the first time are automatically provisioned with `role=user`.

## Architecture & Data Flow

```
Frontend                    Backend                     Google
   │                           │                           │
   │  Click "Sign in with      │                           │
   │  Google"                  │                           │
   │──────────────────────────────────────────────────────▶│
   │                           │                           │
   │◀─────────────────────────────────────── ID token ─────│
   │                           │                           │
   │  POST /api/auth/google    │                           │
   │  { credential: "<token>" }│                           │
   │──────────────────────────▶│                           │
   │                           │  verify token w/ Google   │
   │                           │──────────────────────────▶│
   │                           │◀────── {email, sub, hd} ──│
   │                           │                           │
   │                           │  check hd (if configured) │
   │                           │  find/create User in DB   │
   │                           │  issue JWT tokens         │
   │◀──────────────────────────│                           │
   │  { access_token,          │                           │
   │    refresh_token }        │                           │
```

After this step, the flow is identical to the current system — JWT stored in localStorage, auto-refresh via `/auth/refresh` unchanged.

## Backend Changes

### New endpoint

`POST /api/auth/google` in `kiro/dashboard/routes_auth.py`:

1. Verify Google ID token using `google-auth` library (signature, expiry, audience)
2. Extract `email`, `sub` (google_id), `hd` from token payload
3. If `GOOGLE_ALLOWED_DOMAIN` is set → reject if `hd != GOOGLE_ALLOWED_DOMAIN`
4. Lookup user by `google_id` column in `users` table
5. If not found → create new user: `username=email`, `role=user`, `google_id=sub`, `password_hash=<random unusable>`
6. Return `TokenResponse` (access_token + refresh_token) — identical shape to `/auth/login`

### DB migration

Add 2 nullable columns to `users` table:
- `google_id VARCHAR(255) UNIQUE NULL` — for Google user lookup
- `email VARCHAR(255) NULL` — display email

### Config additions

```bash
# .env
GOOGLE_CLIENT_ID="xxx.apps.googleusercontent.com"
GOOGLE_ALLOWED_DOMAIN=""   # optional, e.g. "company.com" — filters by hd claim
```

```python
# kiro/config.py
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_ALLOWED_DOMAIN: str = os.getenv("GOOGLE_ALLOWED_DOMAIN", "")
```

### New dependency

```
google-auth>=2.0.0
```

### Existing backend preserved

`/auth/login` (username/password) and `/auth/refresh` remain unchanged — admin fallback access still works.

## Frontend Changes

### New package

```
@react-oauth/google
```

### `webui/app/(auth)/login/page.tsx`

Remove username/password form. Replace with:
- Existing logo + title (unchanged)
- `<GoogleLogin>` component — renders the official Google button
- On success: call `loginWithGoogle(credential)` → redirect to `/`
- On error: show error message

### `webui/lib/auth.tsx`

Add `loginWithGoogle` to `AuthContextValue`:

```ts
loginWithGoogle: (credential: string) => Promise<void>
// POST /api/auth/google → setTokens + setUser (same as login)
```

### `webui/lib/providers.tsx`

Wrap with `GoogleOAuthProvider`:

```tsx
<GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID!}>
  {children}
</GoogleOAuthProvider>
```

### `webui/.env.local`

```
NEXT_PUBLIC_GOOGLE_CLIENT_ID="xxx.apps.googleusercontent.com"
```

### Unchanged

`api-client.ts`, JWT refresh interceptor, all dashboard pages, `use-auth.ts` hook.

## Error Handling

| Scenario | Response |
|---|---|
| Invalid/expired Google token | 401 `Invalid Google token` |
| Domain not allowed (`hd` mismatch) | 403 `Access restricted to @{domain} accounts` |
| `GOOGLE_CLIENT_ID` not configured | 500 `Google OAuth not configured` |
| User is inactive in DB | 401 `Account is disabled` |

## Testing

- Unit: mock `google.oauth2.id_token.verify_oauth2_token`, test domain check, auto-provision, inactive user
- E2E: update `global-setup.ts` to use Google login flow (or keep a test user with password for Playwright)

## Google Cloud Console Setup

1. Create OAuth 2.0 Client ID (Web application)
2. Add authorized JavaScript origins: `http://localhost:3000`, `https://your-domain.com`
3. Copy Client ID → `GOOGLE_CLIENT_ID` / `NEXT_PUBLIC_GOOGLE_CLIENT_ID`
4. To restrict by org: set OAuth consent screen to "Internal" (Google Workspace only) **or** use `GOOGLE_ALLOWED_DOMAIN` env var (works for any Google account)
