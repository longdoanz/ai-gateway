# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Gateway is a Python FastAPI reverse proxy providing OpenAI-compatible and Anthropic-compatible APIs for Kiro (AWS CodeWhisperer). It translates requests between API formats and handles authentication, streaming, model resolution, and error handling.

**Stack:** Python 3.10+ / FastAPI / uvicorn / PostgreSQL (optional, for dashboard)

## Essential Commands

### Backend (Python)

```bash
# Run server (default: 0.0.0.0:8000)
python main.py
python main.py --port 9000

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest                                    # All tests

# Run with coverage
pytest --cov=kiro --cov-report=html

# Database migrations (when DATABASE_URL is set)
alembic upgrade head
```

### Frontend (webui/)

```bash
cd webui

# Development
npm run dev          # Start dev server (localhost:3000)
npm run build        # Production build

# E2E tests
npx playwright test                    # All tests
npx playwright test dashboard.spec.ts  # Specific file
npx playwright test --ui               # Interactive mode
```

### Docker

```bash
# Standard gateway only
docker-compose up -d

# Full stack (gateway + postgres + webui)
docker-compose -f docker-compose.apikey.yml up -d
```

## Architecture

### Backend Structure (`kiro/`)

Layered architecture with clear separation:

1. **Routes** (`routes_openai.py`, `routes_anthropic.py`) — FastAPI endpoints, auth validation
2. **Converters** (`converters_*.py`) — Format translation (OpenAI/Anthropic → Kiro)
3. **Streaming** (`streaming_*.py`) — SSE stream processing (Kiro → OpenAI/Anthropic)
4. **Core Services** — `auth.py` (token lifecycle), `http_client.py` (retry logic), `model_resolver.py` (4-layer resolution), `cache.py`
5. **Parsers** — `parsers.py` (AWS event stream), `thinking_parser.py` (FSM for extended thinking)
6. **Models** — `models_openai.py`, `models_anthropic.py` (Pydantic validation)

**Dashboard** (`kiro/dashboard/`): JWT auth, user/key management, analytics — activates when `DATABASE_URL` is set.

**Database** (`kiro/db/`): SQLAlchemy async (PostgreSQL via asyncpg), Alembic migrations.

### Frontend Structure (`webui/`)

Next.js 16 App Router + React 19 + Tailwind CSS v4 + shadcn/ui.

```
webui/
├── app/
│   ├── (auth)/login/         # Login page
│   └── (dashboard)/          # Auth-gated pages
├── lib/
│   ├── api-client.ts         # Axios + JWT auto-refresh
│   ├── auth.tsx              # AuthProvider context
│   └── types.ts              # TypeScript interfaces
└── hooks/                    # React Query hooks (use-users, use-keys, etc.)
```

API proxy: `next.config.js` rewrites `/api/*` to backend (`API_URL` env var).

## Key Patterns

### Per-Request HTTP Clients for Streaming

**Critical**: Always use per-request `httpx.AsyncClient` for streaming to prevent CLOSE_WAIT leaks.

### Model Resolution Pipeline

4-layer resolution in `model_resolver.py`:
1. Normalize name (dashes→dots, strip dates)
2. Check dynamic cache (from /ListAvailableModels)
3. Check hidden models (manual config)
4. Pass-through to Kiro (let Kiro decide)

**Principle**: Gateway, not gatekeeper. Kiro API is the final arbiter.

### Test Network Isolation

**Critical**: All tests are completely isolated from the network. Global fixture `block_all_network_calls` in `tests/conftest.py` blocks all httpx requests. Any real network call will fail the test.

### Authentication Auto-Detection

Auth type detected from credentials:
- Has `clientId`/`clientSecret` → AWS SSO OIDC
- No client credentials → Kiro Desktop Auth

## Code Conventions

- **Naming**: `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants
- **Type hints**: Mandatory on all function parameters and return values
- **Docstrings**: Google style with Args/Returns/Raises
- **Logging**: Use `loguru` (not stdlib logging)
- **Async**: All I/O operations are async/await
- **Error handling**: Catch specific exceptions, never bare `except:`

## Configuration

Loaded from `.env` file (see `.env.example`):

```bash
PROXY_API_KEY="required-secret"           # Required

# Dashboard (optional):
DATABASE_URL="postgresql+asyncpg://user:pass@host/db"
JWT_SECRET="your-jwt-secret"
ENCRYPTION_KEY="32-byte-encryption-key"

# Debug:
DEBUG_MODE="off"  # "off" | "errors" | "all"
```

## API Endpoints

**OpenAI-compatible:**
- `GET /health` — Health check
- `GET /v1/models` — List models
- `POST /v1/chat/completions` — Chat (streaming/non-streaming)

**Anthropic-compatible:**
- `POST /v1/messages` — Messages (streaming/non-streaming)

**Auth:** `Authorization: Bearer {PROXY_API_KEY}` or `x-api-key: {PROXY_API_KEY}`

## Common Tasks

### Adding a New Endpoint

1. Define Pydantic models in `models_*.py`
2. Add route in `routes_*.py`
3. Add converter in `converters_*.py`
4. Add streaming logic in `streaming_*.py`
5. Write tests in `tests/unit/test_routes_*.py`

### Debugging Issues

1. Enable debug logging: `DEBUG_MODE="errors"` in `.env`
2. Check `debug_logs/` directory
3. Run tests: `pytest tests/unit/test_<module>.py -v`

### Making Changes

1. Read files before editing
2. Follow existing patterns
3. Add tests for new functionality
4. Run `pytest -v` before committing
5. Use type hints throughout
6. Add docstrings with Args/Returns

## Important Files

- `AGENTS.md` — Comprehensive AI agent guide (851 lines) — **read for full details**
- `.env.example` — Configuration template (265 lines)
- `tests/conftest.py` — Shared test fixtures
- `kiro/config.py` — Centralized configuration
- `kiro/auth.py` — Authentication manager
- `webui/lib/api-client.ts` — Frontend API client

## Webui Notes

- Next.js 16 has breaking changes — check `node_modules/next/dist/docs/` before writing code
- Uses `output: "standalone"` for Docker builds
- Auth state persisted in `tests/e2e/.auth/state.json` for Playwright
