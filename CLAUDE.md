# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> For full project details, architecture, conventions, and patterns — see **AGENTS.md**.

## Essential Commands

### Backend (Python)

```bash
# Run server (default: 0.0.0.0:18000)
python main.py

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

## Frontend Structure (`webui/`)

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

## Making Changes

1. Read files before editing
2. Follow existing patterns
3. Add tests for new functionality
4. Run `pytest -v` before committing
5. Use type hints throughout
6. Add docstrings with Args/Returns

## Important Files

- `AGENTS.md` — Comprehensive AI agent guide — **read for full details**
- `.env.example` — Configuration template
- `tests/conftest.py` — Shared test fixtures
- `kiro/config.py` — Centralized configuration
- `kiro/auth.py` — Authentication manager
- `webui/lib/api-client.ts` — Frontend API client

## Webui Notes

- Next.js 16 has breaking changes — check `node_modules/next/dist/docs/` before writing code
- Uses `output: "standalone"` for Docker builds
- Auth state persisted in `tests/e2e/.auth/state.json` for Playwright
