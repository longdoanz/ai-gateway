# AGENTS.md - AI Agent Guide for Kiro Gateway

## Project Philosophy

**Transparent proxy with minimal, purposeful modifications.** We expose undocumented Kiro API functionality and work around API quirks. Transparency means being clear about what we add, not refusing to add anything.

### Core Principles

1. **Transparency First** - Preserve user intent, fix API quirks, don't remove user content
2. **Minimal Intervention** - Surgical changes only, every modification must serve a clear purpose
3. **User Control** - All enhancements configurable, users can get native Kiro behavior
4. **Systems Over Patches** - Build abstractions that handle entire classes of issues, not one-off fixes
5. **Paranoid Testing** - Every commit needs tests, test edge cases and failures, not just happy path
6. **Code Quality** - Docstrings (Google style), type hints mandatory, loguru logging, specific exception handling
7. **Feature Parity** - Implement for BOTH OpenAI and Anthropic APIs

## Project Overview

Python FastAPI reverse proxy providing OpenAI/Anthropic-compatible APIs for Kiro (Amazon Q Developer).

- **Stack**: Python 3.10+ / FastAPI / uvicorn / PostgreSQL (optional dashboard)
- **Entry**: `main.py`
- **Package**: `kiro/`

## Essential Commands

```bash
python main.py                    # Server (default: 0.0.0.0:8000)
pytest -v                         # Tests
docker-compose up -d              # Docker
```

## Architecture

**Layered**: Routes → Converters → Streaming → Core Services → Parsers → Models

**Key Components**:
- **Auth** (`auth.py`): 4 methods, auto-detects type, thread-safe refresh
- **Model Resolution** (`model_resolver.py`): 4-layer pipeline, gateway not gatekeeper
- **HTTP Client** (`http_client.py`): Auto-retry, per-request clients for streaming
- **Streaming**: AWS event stream → OpenAI/Anthropic SSE, thinking block extraction

## Code Conventions

- **Naming**: `snake_case` functions/variables, `PascalCase` classes
- **Type hints**: Mandatory on all parameters and return values
- **Docstrings**: Google style with Args/Returns/Raises
- **Logging**: `loguru` (INFO for business logic, DEBUG for technical, ERROR for failures)
- **Error handling**: Catch specific exceptions, never bare `except:`
- **Async**: All I/O operations are async/await

## Testing

**Complete network isolation** - Global fixture blocks all httpx requests. Test edge cases, errors, boundaries - not just happy path.

## Configuration

```bash
PROXY_API_KEY="required-secret"           # Required
DATABASE_URL="postgresql+asyncpg://..."   # Optional dashboard
DEBUG_MODE="off"  # "off" | "errors" | "all"
```

## Critical Patterns

- **Per-request HTTP clients for streaming** - Prevents CLOSE_WAIT leaks
- **Model name normalization** - Client format → Kiro format
- **Auth auto-detection** - Has clientId/clientSecret → AWS SSO OIDC, else → Kiro Desktop

## Common Tasks

**Adding Endpoint**: Define models → Add route → Add converter → Add streaming → Write tests

**Debugging**: Enable `DEBUG_MODE="errors"` → Check `debug_logs/` → Run tests

## API Endpoints

**OpenAI**: `GET /health`, `GET /v1/models`, `POST /v1/chat/completions`

**Anthropic**: `POST /v1/messages`

**Auth**: `Authorization: Bearer {PROXY_API_KEY}` or `x-api-key: {PROXY_API_KEY}`
