# API Key Mode Design

**Date:** 2026-04-23  
**Status:** Approved  
**Scope:** New remote deployment mode where users supply their own Kiro API key per-request

---

## Problem

Current kiro-gateway requires server-side credentials (`REFRESH_TOKEN`, `KIRO_CREDS_FILE`, or `KIRO_CLI_DB_FILE`). This is unsuitable for remote/shared deployments where each user has their own Kiro API key and should authenticate independently.

---

## Solution: `API_KEY_MODE`

A new operating mode activated by `API_KEY_MODE=true`. In this mode:

- The `Authorization: Bearer <token>` header carries the user's **Kiro API key** (not a gateway password)
- No server-side Kiro credentials required
- `KiroAuthManager` and token refresh logic are bypassed entirely
- All new logic lives in `kiro/api_key_mode.py` to minimize upstream conflict surface

---

## Architecture

### Request Flow

```
Client
  Authorization: Bearer <kiro_api_key>
        ↓
FastAPI route (routes_openai.py / routes_anthropic.py)
  if API_KEY_MODE → dispatch to kiro/api_key_mode.py
        ↓
kiro/api_key_mode.py
  extract api_key from header
  build Kiro headers (tokentype: API_KEY, ...)
        ↓
Kiro API  (https://q.{region}.amazonaws.com)
  Authorization: Bearer <kiro_api_key>
  tokentype: API_KEY
```

### Mode Comparison

| Aspect | Normal mode | API_KEY_MODE |
|---|---|---|
| Auth credential | Server-side REFRESH_TOKEN / creds file | User's Kiro API key per-request |
| `PROXY_API_KEY` | Required (gateway password) | Not used |
| `KiroAuthManager` | Created at startup | Not created |
| Token refresh | Automatic | Not needed (API key is long-lived) |
| Multi-user | No | Yes |
| Model list | Fetched at startup with server creds | Lazy-fetched on first `/v1/models` call |

---

## File Changes

### New file: `kiro/api_key_mode.py`

Self-contained module. Does **not** import from `kiro/auth.py` or `kiro/http_client.py`.

Reuses existing converters and streaming helpers (`converters_openai.py`, `converters_core.py`, `streaming_openai.py`, `streaming_anthropic.py`) — no duplication of payload conversion or streaming logic.

**Components:**

1. **`build_kiro_headers_api_key(api_key, x_amz_target)`**  
   Builds Kiro request headers with `tokentype: API_KEY`. Uses the exact header set required for headless API key auth (User-Agent, amz-sdk-invocation-id, etc.).

2. **`get_api_key(auth_header)`** — FastAPI dependency  
   Extracts `Bearer <token>` from Authorization header. Raises 401 if missing or malformed.

3. **`ApiKeyHttpClient`**  
   Simplified HTTP client using `app.state.http_client` (shared connection pool).  
   - 403 → raise 401 immediately (wrong key, no retry)  
   - 429 / 5xx / timeout → exponential backoff retry (same as existing `KiroHttpClient`)

4. **`get_models_cached(api_key, app_state)`**  
   Lazy model cache. On first call (or after TTL expiry), fetches `/ListAvailableModels` using the user's API key. Falls back to `FALLBACK_MODELS` on failure. TTL reuses `MODEL_CACHE_TTL` from config (1 hour).

5. **`handle_chat_api_key(request, request_data)`**  
   Full chat handler for OpenAI-format requests in API_KEY_MODE.

6. **`handle_chat_api_key_anthropic(request, request_data)`**  
   Full chat handler for Anthropic-format requests in API_KEY_MODE.

### Modified: `kiro/config.py`

```python
API_KEY_MODE: bool = os.getenv("API_KEY_MODE", "false").lower() in ("true", "1", "yes")
```

~3 lines added near `PROXY_API_KEY` section.

### Modified: `main.py`

`validate_configuration()`: skip credential check when `API_KEY_MODE=true`.

`lifespan()`:
```python
if not API_KEY_MODE:
    app.state.auth_manager = KiroAuthManager(...)
    # ... existing model fetch logic (unchanged) ...
else:
    app.state.model_cache = ModelInfoCache()  # populated lazily
    logger.info("API_KEY_MODE: credentials provided per-request by users")
```

~10 lines added. Existing code untouched.

### Modified: `kiro/routes_openai.py`

**`verify_api_key` must be mode-aware.** Currently it checks `Bearer {PROXY_API_KEY}` — in `API_KEY_MODE` this would reject all requests before reaching the handler. Fix: make `verify_api_key` a no-op (always pass) when `API_KEY_MODE=true`. The actual key extraction happens inside the handler via `get_api_key()` from `api_key_mode.py`.

```python
# In verify_api_key:
if API_KEY_MODE:
    return True  # auth handled per-handler in api_key_mode.py
if not auth_header or auth_header != f"Bearer {PROXY_API_KEY}":
    raise HTTPException(status_code=401, ...)
```

Dispatch block at top of each handler:
```python
@router.post("/v1/chat/completions")
async def chat_completions(request: Request, ...):
    if API_KEY_MODE:
        from kiro.api_key_mode import handle_chat_api_key
        return await handle_chat_api_key(request, request_data)
    # ... existing code unchanged below ...
```

Same pattern for `/v1/models`. ~5 lines per handler.

### Modified: `kiro/routes_anthropic.py`

Same dispatch pattern. ~5 lines per handler.

### Modified: `docker-compose.yml` + `.env.example`

Add `API_KEY_MODE=false` with explanatory comment.

---

## Region

`KIRO_REGION` env var (default `us-east-1`). Kiro API keys do not encode region, so the server admin sets region once for all users.

---

## Error Handling

| Scenario | Response |
|---|---|
| Missing/malformed Authorization header | 401 `"Missing or invalid Authorization header"` |
| Kiro returns 403 | 401 `"Invalid Kiro API key"` (no retry) |
| Kiro returns 429 | Retry with exponential backoff |
| Kiro returns 5xx | Retry with exponential backoff |
| Model fetch fails | Silent fallback to `FALLBACK_MODELS` |

---

## Upstream Conflict Strategy

- All new logic in `kiro/api_key_mode.py` — upstream never touches this file
- Changes to `routes_*.py` are isolated `if API_KEY_MODE:` dispatch blocks at the top of handlers
- Changes to `main.py` are isolated `if not API_KEY_MODE:` / `else:` blocks in lifespan
- When upstream updates `routes_*.py` or `main.py`, conflicts will be small and mechanical to resolve

---

## Out of Scope

- Per-user rate limiting
- API key validation beyond what Kiro API returns
- Multi-region per-user routing
