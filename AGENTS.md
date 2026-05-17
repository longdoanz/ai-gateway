# AGENTS.md - AI Agent Guide for Kiro Gateway

## Project Philosophy

**Transparent proxy with minimal, purposeful modifications.** We expose undocumented Kiro API functionality and work around API quirks. Transparency means being clear about what we add, not refusing to add anything.

### Core Principles

1. **Transparency First**
   - The gateway preserves the user's original intent and request structure
   - Modifications are made only when necessary to work around Kiro API limitations or to add opt-in enhancements
   - We fix API quirks, not user decisions

2. **Minimal Intervention**
   - Changes to requests are surgical and well-justified
   - We add capabilities (like extended thinking) but never remove user content
   - Every modification must serve a clear purpose: fixing validation issues, adding optional features, or improving compatibility

3. **User Control**
   - All optional enhancements must be configurable
   - Users can disable features to get native Kiro API behavior
   - The gateway respects user choices about conversation structure and content

4. **Clear Boundaries**
   - ✅ **We fix**: API validation quirks, format incompatibilities, authentication flows
   - ✅ **We add (optionally)**: Enhanced features that Kiro API doesn't provide natively
   - ❌ **We don't modify**: User's conversation content, context decisions, message priorities
   - ❌ **We don't decide**: What messages to keep, what to trim, what's "important"

5. **Responsibility Separation**
   - Gateway handles API-level issues
   - Client handles content-level decisions
   - Model handles capacity limitations

6. **Systems Over Patches**
   - When solving a problem, we build systems that handle entire classes of issues, not one-off fixes
   - Even if a quick if-else would work, we invest time in creating proper abstractions and dedicated modules
   - Solutions should be easily extensible without modifying core logic
   - We prefer spending a few extra minutes on architecture that scales over quick hacks that accumulate technical debt
   - Every fix is an opportunity to create infrastructure that prevents similar problems in the future

7. **Paranoid Testing Philosophy**
   - Every commit must include tests - no exceptions
   - Tests exist to break code, not to confirm it works
   - Happy path alone is worthless - we test edge cases, error scenarios, boundary conditions, and malformed inputs
   - If you can't think of ways to break your code, you haven't thought hard enough
   - Two basic tests are not testing - comprehensive coverage means testing every logical branch and failure mode
   - Tests are both documentation and a safety net - they should clearly show what the code does and prevent regressions
   - Check `tests/README.md` to find the appropriate existing `test_*.py` file for your tests - avoid creating new test files unless adding a completely new module

8. **Code Quality Standards**
   - All code, comments, docstrings, and variable names must be in English (except for specific cases like Unicode tests or multilingual examples)
   - Comprehensive docstrings for all functions (Google style with Args/Returns/Raises)
   - Type hints are mandatory - every function parameter and return value must be typed
   - Logging at key decision points using loguru (INFO for business logic, DEBUG for technical details, ERROR for failures)
   - Never use bare `except:` or `except Exception:` - catch specific exceptions and add context
   - Proactive tech debt cleanup - if you see hardcoded values or duplicated code, extract it immediately (constants, functions, modules)
   - No placeholders - every function must be complete and production-ready when committed

9. **User Experience First**
   - Error messages must be actionable and user-friendly, not technical jargon
   - When something fails, explain what went wrong and how to fix it
   - Configuration should be intuitive with sensible defaults
   - Debug logging exists to help users troubleshoot, not just for developers
   - Documentation is part of the feature - if users can't figure it out, it doesn't work
   - Every error should guide the user toward a solution, not leave them confused

10. **Complete Feature Consistency**
   - When adding new functionality, implement it for BOTH OpenAI and Anthropic APIs
   - Changes must be applied to BOTH streaming and non-streaming code paths
   - Both API surfaces must have equal capabilities - no fragmentation
   - Test coverage must include all combinations: OpenAI streaming/non-streaming, Anthropic streaming/non-streaming
   - If a feature only makes sense for one API or one mode, document why explicitly

11. **Pragmatic Transparency**
   - Transparency means being clear about modifications, not refusing to add useful features
   - Response enrichment (adding derived fields) is acceptable if it doesn't break compatibility
   - Clients can ignore added fields - original upstream data is always preserved

### Code Review Reality Check

**Your code quality reveals your approach.** Contributions missing tests, using non-English identifiers, or lacking consistency across architecture and both APIs and streaming modes indicate surface-level work - a quick hack and patch based on assumptions rather than understanding. Such PRs face significant scrutiny and likely rejection.

**What we look for:**
- Comprehensive tests that attempt to break the code, not just confirm it works
- Complete consistency: changes applied to OpenAI + Anthropic, streaming + non-streaming
- Evidence you studied the codebase (using search tools, reading related modules) rather than guessing
- English-only code that integrates naturally with existing patterns

**What signals low effort:**
- "I'll add tests later" or minimal happy-path tests
- Changes to only one API or only one mode
- Non-English variable names or comments
- Code that doesn't match project patterns because you didn't check them

We can tell when you've used basic prompts for a quick fix versus when you've invested time understanding the architecture. The former gets rejected. The latter gets merged.

### About "Improperly formed request" Errors

**Important**: Kiro API's "Improperly formed request" error is notoriously vague due to poor documentation from Amazon. This single error message can indicate many different validation issues:

- Message structure problems (wrong role order, missing required fields)
- Tool definition issues (invalid schemas, name length violations)
- Content format problems (malformed JSON, unsupported content types)
- Authentication or permission issues
- Undocumented API constraints

When debugging this error, systematic testing is required to identify the actual cause. The gateway fixes known validation quirks, but new edge cases may emerge as Kiro API evolves.

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

### Running Tests

```bash
# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_auth_manager.py -v

# Run specific test
pytest tests/unit/test_auth_manager.py::TestKiroAuthManagerInitialization::test_initialization_stores_credentials -v

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v

# Stop on first failure
pytest -x

# Show local variables on errors
pytest -l

# Run with coverage
pip install pytest-cov
pytest --cov=kiro --cov-report=html
```

### Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt

# Main dependencies:
# - fastapi
# - uvicorn[standard]
# - httpx
# - loguru
# - requests
# - python-dotenv
# - tiktoken
# - pytest
# - pytest-asyncio
# - hypothesis
```

### Docker (Containerization)

```bash
# Build Docker image
docker build -t kiro-gateway .

# Run with Docker (using environment variables)
docker run -d \
  -p 8000:8000 \
  -e PROXY_API_KEY="your-secret-key" \
  -e REFRESH_TOKEN="your-refresh-token" \
  --name kiro-gateway \
  kiro-gateway

# Run with docker-compose (recommended)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop container
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# Run with custom .env file
docker-compose --env-file .env.production up -d

# Mount credentials file (Kiro IDE)
docker run -d \
  -p 8000:8000 \
  -v ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro \
  -e KIRO_CREDS_FILE=/home/kiro/.aws/sso/cache/kiro-auth-token.json \
  -e PROXY_API_KEY="your-secret-key" \
  --name kiro-gateway \
  kiro-gateway

# Mount kiro-cli database
docker run -d \
  -p 8000:8000 \
  -v ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli \
  -e KIRO_CLI_DB_FILE=/home/kiro/.local/share/kiro-cli/data.sqlite3 \
  -e PROXY_API_KEY="your-secret-key" \
  --name kiro-gateway \
  kiro-gateway
```

**Docker Features:**
- Single-stage optimized build
- Non-root user (`kiro`) for security
- Health check endpoint monitoring (`/health`)
- Volume mounts for credentials and debug logs
- Automatic restart on failure
- Support for all 4 authentication methods
- Resource limits (optional in docker-compose.yml)

**CI/CD Integration:**
- GitHub Actions workflow (`.github/workflows/docker.yml`)
- Automated testing before Docker build
- Docker image testing (health checks)
- Automatic push to GitHub Container Registry (ghcr.io) on main branch
- Coverage report generation

## Project Structure

```
kiro-gateway/
├── main.py                          # Application entry point
├── kiro/                            # Main package
│   ├── __init__.py                  # Package exports
│   ├── config.py                    # Configuration and constants
│   ├── auth.py                      # Authentication manager
│   ├── account_manager.py           # Account system with Circuit Breaker, sticky behavior, lazy init
│   ├── account_errors.py            # Account error classification
│   ├── cache.py                     # Model metadata cache
│   ├── model_resolver.py            # Dynamic model resolution
│   ├── http_client.py               # HTTP client with retry logic
│   ├── routes_openai.py             # OpenAI API endpoints
│   ├── routes_anthropic.py          # Anthropic API endpoints
│   ├── converters_core.py           # Shared conversion logic
│   ├── converters_openai.py         # OpenAI format converters
│   ├── converters_anthropic.py      # Anthropic format converters
│   ├── streaming_core.py            # Shared streaming logic
│   ├── streaming_openai.py          # OpenAI streaming
│   ├── streaming_anthropic.py       # Anthropic streaming
│   ├── parsers.py                   # AWS SSE stream parsers
│   ├── thinking_parser.py           # Thinking block parser (FSM)
│   ├── models_openai.py             # OpenAI Pydantic models
│   ├── models_anthropic.py          # Anthropic Pydantic models
│   ├── network_errors.py            # Network error classification
│   ├── kiro_errors.py               # Kiro API error enhancement
│   ├── exceptions.py                # Exception handlers
│   ├── payload_guards.py            # Request payload validation
│   ├── truncation_state.py          # Truncation state tracking
│   ├── truncation_recovery.py       # Truncation recovery system
│   ├── mcp_tools.py                 # MCP tools (web_search)
│   ├── debug_logger.py              # Debug logging system
│   ├── debug_middleware.py          # Debug middleware
│   ├── tokenizer.py                 # Token counting (tiktoken)
│   └── utils.py                     # Helper utilities
├── tests/                           # Test suite
│   ├── conftest.py                  # Shared fixtures
│   ├── unit/                        # Unit tests
│   └── integration/                 # Integration tests
├── .env.example                     # Environment configuration template
├── requirements.txt                 # Python dependencies
└── pytest.ini                       # Pytest configuration
```

## Code Architecture

### Modular Design

The codebase follows a layered architecture:

1. **Routes Layer** (`routes_*.py`): FastAPI endpoints, authentication, request validation
2. **Converters Layer** (`converters_*.py`): Format translation (OpenAI/Anthropic → Kiro)
3. **Streaming Layer** (`streaming_*.py`): SSE stream processing (Kiro → OpenAI/Anthropic)
4. **Core Services**: Auth, HTTP client, model resolution, caching
5. **Parsers**: AWS event stream parsing, thinking block extraction
6. **Models**: Pydantic models for validation

### Key Components

#### Authentication (`auth.py`)

- **KiroAuthManager**: Manages token lifecycle
- Supports multiple auth methods:
  - JSON credentials file (Kiro IDE)
  - Environment variables (refresh token)
  - SQLite database (kiro-cli)
  - AWS SSO OIDC (Builder ID, Enterprise)
- Auto-detects auth type based on credentials
- Thread-safe token refresh with asyncio.Lock
- Automatic refresh before expiration

#### Model Resolution (`model_resolver.py`)

4-layer resolution pipeline:
1. **Normalize Name**: Convert client formats to Kiro format (dashes→dots, strip dates)
2. **Check Dynamic Cache**: Models from /ListAvailableModels API
3. **Check Hidden Models**: Manual config for undocumented models
4. **Pass-through**: Unknown models sent to Kiro (let Kiro decide)

Key principle: **We are a gateway, not a gatekeeper**. Kiro API is the final arbiter.

#### HTTP Client (`http_client.py`)

- **KiroHttpClient**: HTTP client with automatic retry logic
- Handles errors:
  - 403: Automatic token refresh and retry
  - 429: Exponential backoff
  - 5xx: Exponential backoff
  - Timeouts: Exponential backoff
- Supports per-request clients (for streaming) and shared clients (for connection pooling)
- Network error classification with user-friendly messages

#### Streaming (`streaming_*.py`)

- Parses AWS event stream format
- Converts to OpenAI or Anthropic SSE format
- Handles thinking blocks (extended thinking mode)
- First token timeout with retry logic
- Tool call parsing and deduplication

#### Converters (`converters_*.py`)

- **Core Layer** (`converters_core.py`): Shared logic for both APIs
  - UnifiedMessage format
  - Tool processing and sanitization
  - Message merging
  - Kiro payload building
- **OpenAI Adapter** (`converters_openai.py`): OpenAI → Kiro
- **Anthropic Adapter** (`converters_anthropic.py`): Anthropic → Kiro

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

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
