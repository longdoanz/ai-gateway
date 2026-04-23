# API Key Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `API_KEY_MODE` — a new operating mode where users supply their own Kiro API key per-request via `Authorization: Bearer <kiro_api_key>`, enabling remote/shared deployments without server-side credentials.

**Architecture:** All new logic lives in `kiro/api_key_mode.py` (self-contained, no imports from `kiro/auth.py`). Existing routes dispatch to this module via a single `if API_KEY_MODE:` block at the top of each handler, leaving the rest of the handler untouched. `verify_api_key` / `verify_anthropic_api_key` become mode-aware no-ops in `API_KEY_MODE`.

**Tech Stack:** Python 3.10, FastAPI, httpx, loguru — same as existing codebase.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `kiro/api_key_mode.py` | **Create** | All API key mode logic: header builder, auth dependency, HTTP client, model cache, chat handlers |
| `kiro/config.py` | Modify | Add `API_KEY_MODE` flag |
| `main.py` | Modify | Skip auth_manager init + credential validation in API_KEY_MODE |
| `kiro/routes_openai.py` | Modify | Make `verify_api_key` mode-aware; dispatch to `api_key_mode` in handlers |
| `kiro/routes_anthropic.py` | Modify | Make `verify_anthropic_api_key` mode-aware; dispatch to `api_key_mode` in handlers |
| `docker-compose.yml` | Modify | Add `API_KEY_MODE` env var |
| `.env.example` | Modify | Document `API_KEY_MODE` |
| `tests/unit/test_api_key_mode.py` | **Create** | Unit tests for `api_key_mode.py` |

---

## Task 1: Add API_KEY_MODE flag to config

**Files:**
- Modify: `kiro/config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_config.py — add to existing file
def test_api_key_mode_default_false(monkeypatch):
    monkeypatch.delenv("API_KEY_MODE", raising=False)
    import importlib, kiro.config as cfg
    importlib.reload(cfg)
    assert cfg.API_KEY_MODE is False

def test_api_key_mode_true_when_set(monkeypatch):
    monkeypatch.setenv("API_KEY_MODE", "true")
    import importlib, kiro.config as cfg
    importlib.reload(cfg)
    assert cfg.API_KEY_MODE is True
```

- [ ] **Step 2: Run to verify fails**

```bash
.venv/bin/pytest tests/unit/test_config.py::test_api_key_mode_default_false -v
```
Expected: `AttributeError: module 'kiro.config' has no attribute 'API_KEY_MODE'`

- [ ] **Step 3: Add to config.py after PROXY_API_KEY line (~line 99)**

```python
# API Key Mode - users supply their own Kiro API key per-request
# When enabled: Authorization: Bearer <kiro_api_key> is forwarded directly to Kiro
# Server-side credentials (REFRESH_TOKEN, KIRO_CREDS_FILE, KIRO_CLI_DB_FILE) not required
API_KEY_MODE: bool = os.getenv("API_KEY_MODE", "false").lower() in ("true", "1", "yes")
```

Also add `API_KEY_MODE` to the imports in `main.py` (just add to the existing import block from `kiro.config`).

- [ ] **Step 4: Run tests**

```bash
cd /data/longdt/kiro-gateway && .venv/bin/pytest tests/unit/test_config.py::test_api_key_mode_default_false tests/unit/test_config.py::test_api_key_mode_true_when_set -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add kiro/config.py && git commit -m "feat(api-key-mode): add API_KEY_MODE config flag"
```


## Task 2: Create kiro/api_key_mode.py

**Files:**
- Create: `kiro/api_key_mode.py`
- Create: `tests/unit/test_api_key_mode.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_api_key_mode.py
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

# --- test build_kiro_headers_api_key ---

def test_build_headers_has_tokentype():
    from kiro.api_key_mode import build_kiro_headers_api_key
    headers = build_kiro_headers_api_key("mykey", "SomeTarget")
    assert headers["tokentype"] == "API_KEY"

def test_build_headers_authorization():
    from kiro.api_key_mode import build_kiro_headers_api_key
    headers = build_kiro_headers_api_key("mykey", "SomeTarget")
    assert headers["Authorization"] == "Bearer mykey"

def test_build_headers_x_amz_target():
    from kiro.api_key_mode import build_kiro_headers_api_key
    headers = build_kiro_headers_api_key("mykey", "SomeTarget")
    assert headers["x-amz-target"] == "SomeTarget"

def test_build_headers_has_invocation_id():
    from kiro.api_key_mode import build_kiro_headers_api_key
    headers = build_kiro_headers_api_key("mykey", "SomeTarget")
    # Must be a valid UUID
    uuid.UUID(headers["amz-sdk-invocation-id"])

# --- test extract_api_key ---

@pytest.mark.asyncio
async def test_extract_api_key_valid():
    from kiro.api_key_mode import extract_api_key
    key = await extract_api_key("Bearer mytoken123")
    assert key == "mytoken123"

@pytest.mark.asyncio
async def test_extract_api_key_missing_raises_401():
    from kiro.api_key_mode import extract_api_key
    with pytest.raises(HTTPException) as exc:
        await extract_api_key(None)
    assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_extract_api_key_no_bearer_raises_401():
    from kiro.api_key_mode import extract_api_key
    with pytest.raises(HTTPException) as exc:
        await extract_api_key("mytoken123")
    assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_extract_api_key_empty_token_raises_401():
    from kiro.api_key_mode import extract_api_key
    with pytest.raises(HTTPException) as exc:
        await extract_api_key("Bearer ")
    assert exc.value.status_code == 401

# --- test get_models_cached ---

@pytest.mark.asyncio
async def test_get_models_cached_returns_fallback_on_fetch_failure():
    from kiro.api_key_mode import get_models_cached
    from kiro.config import FALLBACK_MODELS

    mock_state = MagicMock()
    mock_state.api_key_model_cache = None  # no cache yet

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_state.http_client = mock_client

    models = await get_models_cached("badkey", mock_state)
    assert models == FALLBACK_MODELS
```

- [ ] **Step 2: Run to verify fails**

```bash
.venv/bin/pytest tests/unit/test_api_key_mode.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'kiro.api_key_mode'`

- [ ] **Step 3: Create kiro/api_key_mode.py**

```python
# kiro/api_key_mode.py
"""
API Key Mode — per-request Kiro API key authentication.

Users supply their Kiro API key in Authorization: Bearer <key>.
No server-side credentials or token refresh needed.
"""
import time
import uuid
from typing import Optional

import httpx
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from loguru import logger

from kiro.config import (
    FALLBACK_MODELS,
    HIDDEN_MODELS,
    MODEL_CACHE_TTL,
    REGION,
    FIRST_TOKEN_MAX_RETRIES,
    BASE_RETRY_DELAY,
    MAX_RETRIES,
)
from kiro.utils import generate_conversation_id

# ── Constants ────────────────────────────────────────────────────────────────

KIRO_API_HOST = f"https://q.{REGION}.amazonaws.com"
KIRO_USER_AGENT = (
    "aws-sdk-rust/1.3.14 ua/2.1 api/codewhispererstreaming/0.1.14474 "
    "os/linux lang/rust/1.92.0 md/appVersion-2.0.0 app/AmazonQ-For-CLI"
)
X_AMZ_TARGET_CHAT = "AmazonCodeWhispererStreamingService.GenerateAssistantResponse"
X_AMZ_TARGET_LIST_MODELS = "AmazonCodeWhispererService.ListAvailableModels"

_api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

# ── Header builder ────────────────────────────────────────────────────────────

def build_kiro_headers_api_key(api_key: str, x_amz_target: str) -> dict:
    """Build Kiro request headers for API key auth (tokentype: API_KEY)."""
    return {
        "Authorization": f"Bearer {api_key}",
        "tokentype": "API_KEY",
        "Content-Type": "application/x-amz-json-1.0",
        "x-amz-target": x_amz_target,
        "x-amzn-codewhisperer-optout": "false",
        "User-Agent": KIRO_USER_AGENT,
        "x-amz-user-agent": KIRO_USER_AGENT,
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=3",
        "Accept": "*/*",
    }

# ── Auth dependency ───────────────────────────────────────────────────────────

async def extract_api_key(auth_header: Optional[str] = Security(_api_key_header)) -> str:
    """Extract Kiro API key from Authorization: Bearer <key> header."""
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Expected: Bearer <kiro_api_key>")
    token = auth_header[len("Bearer "):]
    if not token.strip():
        raise HTTPException(status_code=401, detail="Empty API key in Authorization header")
    return token

# ── Model cache ───────────────────────────────────────────────────────────────

# Simple in-process cache: (models_list, fetched_at_timestamp)
_model_cache: Optional[tuple] = None

async def get_models_cached(api_key: str, app_state) -> list:
    """
    Return model list, fetching from Kiro if cache is stale.
    Falls back to FALLBACK_MODELS on any error.
    """
    global _model_cache
    now = time.time()

    if _model_cache is not None:
        models, fetched_at = _model_cache
        if now - fetched_at < MODEL_CACHE_TTL:
            return models

    try:
        headers = build_kiro_headers_api_key(api_key, X_AMZ_TARGET_LIST_MODELS)
        url = f"{KIRO_API_HOST}/ListAvailableModels"
        response = await app_state.http_client.get(url, headers=headers, params={"origin": "AI_EDITOR"})
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", FALLBACK_MODELS)
            _model_cache = (models, now)
            return models
        logger.warning(f"API_KEY_MODE: ListAvailableModels returned {response.status_code}, using fallback")
    except Exception as e:
        logger.warning(f"API_KEY_MODE: model fetch failed ({e}), using fallback")

    return FALLBACK_MODELS

# ── HTTP client ───────────────────────────────────────────────────────────────

import asyncio

class ApiKeyHttpClient:
    """
    Simplified HTTP client for API_KEY_MODE.
    No token refresh — 403 means bad key, raise immediately.
    Retries 429/5xx/timeout with exponential backoff.
    """

    def __init__(self, shared_client: httpx.AsyncClient):
        self._client = shared_client

    async def request_with_retry(
        self,
        method: str,
        url: str,
        api_key: str,
        json_data: dict,
        stream: bool = False,
    ) -> httpx.Response:
        max_retries = FIRST_TOKEN_MAX_RETRIES if stream else MAX_RETRIES
        headers = build_kiro_headers_api_key(api_key, X_AMZ_TARGET_CHAT)
        if stream:
            headers["Connection"] = "close"

        for attempt in range(max_retries):
            try:
                if stream:
                    req = self._client.build_request(method, url, json=json_data, headers=headers)
                    response = await self._client.send(req, stream=True)
                else:
                    response = await self._client.request(method, url, json=json_data, headers=headers)

                if response.status_code == 200:
                    return response
                if response.status_code == 403:
                    raise HTTPException(status_code=401, detail="Invalid Kiro API key (403 from Kiro API)")
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(BASE_RETRY_DELAY * (2 ** attempt))
                        continue
                return response

            except HTTPException:
                raise
            except (httpx.TimeoutException, httpx.RequestError) as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(BASE_RETRY_DELAY * (2 ** attempt))
                else:
                    raise HTTPException(status_code=504, detail=f"Kiro API unreachable: {e}")

        raise HTTPException(status_code=502, detail="Kiro API request failed after retries")
```

- [ ] **Step 4: Run tests**

```bash
cd /data/longdt/kiro-gateway && .venv/bin/pytest tests/unit/test_api_key_mode.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add kiro/api_key_mode.py tests/unit/test_api_key_mode.py && git commit -m "feat(api-key-mode): add api_key_mode module with header builder, auth dependency, HTTP client, model cache"
```


## Task 3: Add chat handlers to kiro/api_key_mode.py

**Files:**
- Modify: `kiro/api_key_mode.py`
- Modify: `tests/unit/test_api_key_mode.py`

The handlers reuse existing converters and streaming functions. An `ApiKeyAuthAdapter` provides the `KiroAuthManager` interface needed by streaming functions (for MCP tool calls). Note: MCP web search in API_KEY_MODE uses the api_key as bearer token without `tokentype: API_KEY` — calls may fail gracefully if Kiro rejects them.

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/unit/test_api_key_mode.py

@pytest.mark.asyncio
async def test_api_key_auth_adapter_get_access_token():
    from kiro.api_key_mode import ApiKeyAuthAdapter
    adapter = ApiKeyAuthAdapter("mykey123")
    token = await adapter.get_access_token()
    assert token == "mykey123"

def test_api_key_auth_adapter_hosts():
    from kiro.api_key_mode import ApiKeyAuthAdapter, KIRO_API_HOST
    adapter = ApiKeyAuthAdapter("mykey123")
    assert adapter.api_host == KIRO_API_HOST
    assert adapter.q_host == KIRO_API_HOST

def test_api_key_auth_adapter_profile_arn_none():
    from kiro.api_key_mode import ApiKeyAuthAdapter
    adapter = ApiKeyAuthAdapter("mykey123")
    assert adapter.profile_arn is None
```

- [ ] **Step 2: Run to verify fails**

```bash
.venv/bin/pytest tests/unit/test_api_key_mode.py::test_api_key_auth_adapter_get_access_token -v
```
Expected: `ImportError: cannot import name 'ApiKeyAuthAdapter'`

- [ ] **Step 3: Append to kiro/api_key_mode.py**

```python
# ── Auth adapter (provides KiroAuthManager interface for streaming functions) ──

class ApiKeyAuthAdapter:
    """
    Minimal adapter implementing the KiroAuthManager interface.
    Used to pass into existing streaming functions without modification.
    get_access_token() returns the api_key directly (no refresh needed).
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self.api_host = KIRO_API_HOST
        self.q_host = KIRO_API_HOST
        self.fingerprint = "api-key-mode"
        self.profile_arn = None
        # Not KIRO_DESKTOP — prevents profileArn from being added to payload
        self.auth_type = None

    async def get_access_token(self) -> str:
        return self._api_key

    async def force_refresh(self) -> None:
        pass  # No-op: API keys don't expire/refresh


# ── OpenAI chat handler ───────────────────────────────────────────────────────

async def handle_chat_openai(request, request_data):
    """
    Handle POST /v1/chat/completions in API_KEY_MODE.
    Reuses existing converters and streaming functions.
    """
    import json
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse
    from kiro.converters_openai import build_kiro_payload
    from kiro.streaming_openai import stream_with_first_token_retry, collect_stream_response
    from kiro.utils import generate_conversation_id
    from kiro.config import WEB_SEARCH_ENABLED
    from kiro.cache import ModelInfoCache

    auth_header = request.headers.get("Authorization")
    api_key = await extract_api_key(auth_header)
    adapter = ApiKeyAuthAdapter(api_key)

    # Auto-inject web_search tool if enabled
    if WEB_SEARCH_ENABLED and request_data.tools is None:
        request_data.tools = []
    if WEB_SEARCH_ENABLED:
        has_ws = any(
            getattr(t, "type", None) == "function" and
            getattr(getattr(t, "function", None), "name", None) == "web_search"
            for t in request_data.tools
        )
        if not has_ws:
            from kiro.models_openai import Tool, ToolFunction
            request_data.tools.append(Tool(
                type="function",
                function=ToolFunction(
                    name="web_search",
                    description="Search the web for current information.",
                    parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
                )
            ))

    conversation_id = generate_conversation_id()
    try:
        kiro_payload = build_kiro_payload(request_data, conversation_id, "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    url = f"{KIRO_API_HOST}/generateAssistantResponse"
    model_cache: ModelInfoCache = request.app.state.model_cache
    shared_client = request.app.state.http_client
    http_client = ApiKeyHttpClient(shared_client)

    response = await http_client.request_with_retry("POST", url, api_key, kiro_payload, stream=True)

    if response.status_code != 200:
        error_content = await response.aread()
        error_text = error_content.decode("utf-8", errors="replace")
        return JSONResponse(status_code=response.status_code, content={
            "error": {"message": error_text, "type": "kiro_api_error", "code": response.status_code}
        })

    messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
    tools_for_tokenizer = [t.model_dump() for t in request_data.tools] if request_data.tools else None

    if request_data.stream:
        async def stream_wrapper():
            try:
                async def make_retry_request():
                    return await http_client.request_with_retry("POST", url, api_key, kiro_payload, stream=True)
                async for chunk in stream_with_first_token_retry(
                    make_request=make_retry_request,
                    client=shared_client,
                    model=request_data.model,
                    model_cache=model_cache,
                    auth_manager=adapter,
                    initial_response=response,
                    request_messages=messages_for_tokenizer,
                    request_tools=tools_for_tokenizer,
                ):
                    yield chunk
            except Exception:
                yield "data: [DONE]\n\n"
                raise
        return StreamingResponse(stream_wrapper(), media_type="text/event-stream")
    else:
        openai_response = await collect_stream_response(
            shared_client, response, request_data.model, model_cache, adapter,
            request_messages=messages_for_tokenizer, request_tools=tools_for_tokenizer
        )
        return JSONResponse(content=openai_response)


# ── Anthropic chat handler ────────────────────────────────────────────────────

async def handle_chat_anthropic(request, request_data):
    """
    Handle POST /v1/messages in API_KEY_MODE.
    Reuses existing converters and streaming functions.
    """
    import json
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse
    from kiro.converters_anthropic import anthropic_to_kiro
    from kiro.streaming_anthropic import stream_with_first_token_retry_anthropic, collect_anthropic_response
    from kiro.utils import generate_conversation_id
    from kiro.cache import ModelInfoCache

    # Anthropic clients use x-api-key header
    api_key = request.headers.get("x-api-key")
    if not api_key:
        auth_header = request.headers.get("Authorization")
        api_key = await extract_api_key(auth_header)

    adapter = ApiKeyAuthAdapter(api_key)
    conversation_id = generate_conversation_id()

    try:
        kiro_payload = anthropic_to_kiro(request_data, conversation_id, "")
    except ValueError as e:
        return JSONResponse(status_code=400, content={"type": "error", "error": {"type": "invalid_request_error", "message": str(e)}})

    url = f"{KIRO_API_HOST}/generateAssistantResponse"
    model_cache: ModelInfoCache = request.app.state.model_cache
    shared_client = request.app.state.http_client
    http_client = ApiKeyHttpClient(shared_client)

    response = await http_client.request_with_retry("POST", url, api_key, kiro_payload, stream=True)

    if response.status_code != 200:
        error_content = await response.aread()
        error_text = error_content.decode("utf-8", errors="replace")
        return JSONResponse(status_code=response.status_code, content={
            "type": "error", "error": {"type": "api_error", "message": error_text}
        })

    messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
    tools_for_tokenizer = [t.model_dump() for t in request_data.tools] if request_data.tools else None
    system_for_tokenizer = (
        [b.model_dump() if hasattr(b, "model_dump") else b for b in request_data.system]
        if isinstance(request_data.system, list) else request_data.system
    )

    if request_data.stream:
        async def stream_wrapper():
            try:
                async def make_retry_request():
                    return await http_client.request_with_retry("POST", url, api_key, kiro_payload, stream=True)
                async for chunk in stream_with_first_token_retry_anthropic(
                    make_request=make_retry_request,
                    model=request_data.model,
                    model_cache=model_cache,
                    auth_manager=adapter,
                    initial_response=response,
                    request_messages=messages_for_tokenizer,
                    request_tools=tools_for_tokenizer,
                    request_system=system_for_tokenizer,
                ):
                    yield chunk
            except Exception:
                yield "data: [DONE]\n\n"
                raise
        return StreamingResponse(stream_wrapper(), media_type="text/event-stream")
    else:
        anthropic_response = await collect_anthropic_response(
            shared_client, response, request_data.model, model_cache, adapter,
            request_messages=messages_for_tokenizer,
            request_tools=tools_for_tokenizer,
            request_system=system_for_tokenizer,
        )
        return JSONResponse(content=anthropic_response)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/unit/test_api_key_mode.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add kiro/api_key_mode.py tests/unit/test_api_key_mode.py && git commit -m "feat(api-key-mode): add ApiKeyAuthAdapter and chat handlers (OpenAI + Anthropic)"
```


## Task 4: Update main.py — skip auth_manager in API_KEY_MODE

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add API_KEY_MODE to imports in main.py**

Find the existing import block from `kiro.config` (around line 59) and add `API_KEY_MODE`:

```python
from kiro.config import (
    APP_TITLE,
    APP_DESCRIPTION,
    APP_VERSION,
    REFRESH_TOKEN,
    PROFILE_ARN,
    REGION,
    KIRO_CREDS_FILE,
    KIRO_CLI_DB_FILE,
    PROXY_API_KEY,
    LOG_LEVEL,
    SERVER_HOST,
    SERVER_PORT,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    STREAMING_READ_TIMEOUT,
    HIDDEN_MODELS,
    MODEL_ALIASES,
    HIDDEN_FROM_LIST,
    FALLBACK_MODELS,
    VPN_PROXY_URL,
    API_KEY_MODE,          # ← add this line
    _warn_timeout_configuration,
)
```

- [ ] **Step 2: Update validate_configuration() to skip credential check**

Find the block starting with `if not has_refresh_token and not has_creds_file and not has_cli_db:` (around line 240) and wrap it:

```python
    if not API_KEY_MODE and not has_refresh_token and not has_creds_file and not has_cli_db:
        # ... existing error block unchanged ...
```

- [ ] **Step 3: Update lifespan() to skip auth_manager creation**

Find the `# Create AuthManager` block (around line 340) and wrap with `if not API_KEY_MODE`:

```python
    if not API_KEY_MODE:
        app.state.auth_manager = KiroAuthManager(
            refresh_token=REFRESH_TOKEN,
            profile_arn=PROFILE_ARN,
            region=REGION,
            creds_file=KIRO_CREDS_FILE if KIRO_CREDS_FILE else None,
            sqlite_db=KIRO_CLI_DB_FILE if KIRO_CLI_DB_FILE else None,
        )
    else:
        app.state.auth_manager = None
        logger.info("API_KEY_MODE enabled: credentials provided per-request by users")
```

Also wrap the model-fetch-at-startup block (the `try:` block that calls `get_access_token()` and `ListAvailableModels`) with `if not API_KEY_MODE:`:

```python
    if not API_KEY_MODE:
        logger.info("Loading models from Kiro API...")
        try:
            # ... existing model fetch block unchanged ...
        except Exception as e:
            # ... existing fallback block unchanged ...
        # ... hidden models + model resolver setup unchanged ...
    else:
        # API_KEY_MODE: model list fetched lazily on first /v1/models call
        await app.state.model_cache.update(FALLBACK_MODELS)
        for display_name, internal_id in HIDDEN_MODELS.items():
            app.state.model_cache.add_hidden_model(display_name, internal_id)
        app.state.model_resolver = ModelResolver(
            cache=app.state.model_cache,
            hidden_models=HIDDEN_MODELS,
            aliases=MODEL_ALIASES,
            hidden_from_list=HIDDEN_FROM_LIST,
        )
        logger.info("API_KEY_MODE: model cache pre-loaded with fallback models (lazy fetch on /v1/models)")
```

- [ ] **Step 4: Run existing tests to verify nothing broke**

```bash
.venv/bin/pytest tests/unit/test_main_cli.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add main.py && git commit -m "feat(api-key-mode): skip auth_manager init and credential validation in API_KEY_MODE"
```


## Task 5: Update routes_openai.py — mode-aware auth + dispatch

**Files:**
- Modify: `kiro/routes_openai.py`

- [ ] **Step 1: Add API_KEY_MODE to imports**

In the existing `from kiro.config import (...)` block (around line 38), add:
```python
from kiro.config import (
    PROXY_API_KEY,
    APP_VERSION,
    API_KEY_MODE,   # ← add
)
```

- [ ] **Step 2: Make verify_api_key mode-aware**

Find `verify_api_key` function (around line 67) and add the early return at the top:

```python
async def verify_api_key(auth_header: str = Security(api_key_header)) -> bool:
    if API_KEY_MODE:
        return True  # auth handled per-handler via extract_api_key in api_key_mode.py
    if not auth_header or auth_header != f"Bearer {PROXY_API_KEY}":
        logger.warning("Access attempt with invalid API key.")
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return True
```

- [ ] **Step 3: Dispatch /v1/models to api_key_mode**

Find the `@router.get("/v1/models", ...)` handler (around line 121). Add dispatch at the top of the function body:

```python
@router.get("/v1/models", response_model=ModelList, dependencies=[Depends(verify_api_key)])
async def list_models(request: Request):
    if API_KEY_MODE:
        from kiro.api_key_mode import get_models_cached, extract_api_key
        from kiro.config import MODEL_ALIASES, HIDDEN_FROM_LIST
        auth_header = request.headers.get("Authorization")
        api_key = await extract_api_key(auth_header)
        raw_models = await get_models_cached(api_key, request.app.state)
        model_resolver = request.app.state.model_resolver
        return model_resolver.get_model_list()
    # ... existing code unchanged below ...
```

- [ ] **Step 4: Dispatch /v1/chat/completions to api_key_mode**

Find `@router.post("/v1/chat/completions", ...)` handler (around line 155). Add dispatch at the very top of the function body (before the `logger.info` line):

```python
@router.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request, request_data: ChatCompletionRequest):
    if API_KEY_MODE:
        from kiro.api_key_mode import handle_chat_openai
        return await handle_chat_openai(request, request_data)
    # ... existing code unchanged below ...
```

- [ ] **Step 5: Run existing route tests**

```bash
.venv/bin/pytest tests/unit/test_routes_openai.py -v 2>&1 | tail -20
```
Expected: all PASS (normal mode tests unaffected)

- [ ] **Step 6: Commit**

```bash
git add kiro/routes_openai.py && git commit -m "feat(api-key-mode): make verify_api_key mode-aware and dispatch to api_key_mode handlers"
```


## Task 6: Update routes_anthropic.py — mode-aware auth + dispatch

**Files:**
- Modify: `kiro/routes_anthropic.py`

- [ ] **Step 1: Add API_KEY_MODE to imports**

In the existing `from kiro.config import PROXY_API_KEY` line (around line 37), expand to:
```python
from kiro.config import PROXY_API_KEY, API_KEY_MODE
```

- [ ] **Step 2: Make verify_anthropic_api_key mode-aware**

Find `verify_anthropic_api_key` function (around line 72). Add early return at the top:

```python
async def verify_anthropic_api_key(
    x_api_key: Optional[str] = Security(anthropic_api_key_header),
    authorization: Optional[str] = Security(auth_header)
) -> bool:
    if API_KEY_MODE:
        return True  # auth handled per-handler in api_key_mode.py
    if x_api_key and x_api_key == PROXY_API_KEY:
        return True
    if authorization and authorization == f"Bearer {PROXY_API_KEY}":
        return True
    logger.warning("Access attempt with invalid API key (Anthropic endpoint)")
    raise HTTPException(
        status_code=401,
        detail={
            "type": "error",
            "error": {
                "type": "authentication_error",
                "message": "Invalid or missing API key. Use x-api-key header or Authorization: Bearer."
            }
        }
    )
```

- [ ] **Step 3: Dispatch /v1/messages to api_key_mode**

Find `@router.post("/v1/messages", ...)` handler (around line 120). Add dispatch at the very top of the function body (before the `logger.info` line):

```python
@router.post("/v1/messages", dependencies=[Depends(verify_anthropic_api_key)])
async def messages(
    request: Request,
    request_data: AnthropicMessagesRequest,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version")
):
    if API_KEY_MODE:
        from kiro.api_key_mode import handle_chat_anthropic
        return await handle_chat_anthropic(request, request_data)
    # ... existing code unchanged below ...
```

- [ ] **Step 4: Run existing route tests**

```bash
.venv/bin/pytest tests/unit/test_routes_anthropic.py -v 2>&1 | tail -20
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add kiro/routes_anthropic.py && git commit -m "feat(api-key-mode): make verify_anthropic_api_key mode-aware and dispatch to api_key_mode handler"
```


## Task 7: Update docker-compose.yml and .env.example

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Add API_KEY_MODE to docker-compose.yml**

Find the `environment:` block in `docker-compose.yml`. After the `PROXY_API_KEY` line, add:

```yaml
      # API Key Mode - users supply their own Kiro API key per-request
      # When enabled: no server-side credentials needed, PROXY_API_KEY not used
      # Each user passes their Kiro API key as: Authorization: Bearer <kiro_api_key>
      - API_KEY_MODE=${API_KEY_MODE:-false}
```

- [ ] **Step 2: Add API_KEY_MODE to .env.example**

Find the `PROXY_API_KEY` section in `.env.example` and add after it:

```bash
# API Key Mode (for remote/shared deployments)
# When true: users supply their own Kiro API key per-request
#   - No server-side credentials required (REFRESH_TOKEN etc. not needed)
#   - PROXY_API_KEY is not used for auth
#   - Client sends: Authorization: Bearer <kiro_api_key>
#   - Kiro API key can be obtained from Kiro IDE settings
# Default: false (use server-side credentials)
API_KEY_MODE=false
```

- [ ] **Step 3: Verify docker-compose syntax**

```bash
docker compose -f /data/longdt/kiro-gateway/docker-compose.yml config > /dev/null && echo "OK"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example && git commit -m "feat(api-key-mode): document API_KEY_MODE in docker-compose and .env.example"
```


## Task 8: Full test suite + smoke test

**Files:**
- No new files

- [ ] **Step 1: Run full unit test suite**

```bash
.venv/bin/pytest tests/unit/ -v 2>&1 | tail -30
```
Expected: all PASS, no regressions in existing tests.

- [ ] **Step 2: Verify API_KEY_MODE=false (normal mode) still works**

```bash
API_KEY_MODE=false .venv/bin/pytest tests/unit/test_routes_openai.py tests/unit/test_routes_anthropic.py -v 2>&1 | tail -20
```
Expected: all PASS

- [ ] **Step 3: Verify API_KEY_MODE=true skips credential validation**

```python
# Quick smoke test — run inline
import os
os.environ["API_KEY_MODE"] = "true"
os.environ["REFRESH_TOKEN"] = ""
os.environ["KIRO_CREDS_FILE"] = ""
os.environ["KIRO_CLI_DB_FILE"] = ""

import importlib
import kiro.config as cfg
importlib.reload(cfg)

assert cfg.API_KEY_MODE is True
print("API_KEY_MODE=true: OK")
```

Run:
```bash
.venv/bin/python -c "
import os; os.environ['API_KEY_MODE']='true'
import importlib, kiro.config as cfg; importlib.reload(cfg)
assert cfg.API_KEY_MODE is True
print('API_KEY_MODE flag: OK')
"
```
Expected: `API_KEY_MODE flag: OK`

- [ ] **Step 4: Verify extract_api_key rejects missing header**

```bash
.venv/bin/python -c "
import asyncio
from kiro.api_key_mode import extract_api_key
from fastapi import HTTPException
async def test():
    try:
        await extract_api_key(None)
        print('FAIL: should have raised')
    except HTTPException as e:
        assert e.status_code == 401
        print('extract_api_key rejects None: OK')
asyncio.run(test())
"
```
Expected: `extract_api_key rejects None: OK`

- [ ] **Step 5: Final commit**

```bash
git add -A && git status
# Verify only expected files are staged, then:
git commit -m "feat(api-key-mode): complete implementation — remote deployment mode with per-request Kiro API key auth"
```

