# Medical Triage Assistant

Production-grade AI triage platform — RAG over clinical guidelines (WHO, NICE, CDC), 7-layer restriction pipeline, real-time SSE streaming, JWT + refresh-token auth, OpenTelemetry tracing.

## Stack

| Layer | Tech | Notes |
|---|---|---|
| Frontend | Next.js 16 + React 19 + Tailwind v4 | SSE streaming, session sidebar, intake form |
| Backend | FastAPI + Python 3.12 | uv-managed, uvloop + httptools |
| Package manager | uv 0.4 | 10–100× faster than pip, lockfile-based |
| RAG | LangChain + pgvector HNSW + text-embedding-3-large | MMR retrieval, similarity gate |
| LLM | Fine-tuned gpt-4o-mini + gpt-4o judge | JSON mode, streaming |
| Queue | Celery + Redis | Async guideline ingestion |
| DB | PostgreSQL 16 + pgvector | RLS append-only audit trail |
| Auth | JWT access tokens + httpOnly refresh tokens | SHA-256 stored, token rotation |
| Observability | Langfuse + OpenTelemetry + collector | Auto-instrumented FastAPI/psycopg/Redis |

## Quick Start

```bash
# 1. Copy and fill env vars
cp .env.example .env
# Set: OPENAI_API_KEY, JWT_SECRET_KEY, INTERNAL_API_KEY, POSTGRES_PASSWORD

# 2. Generate uv lockfile (first time)
cd backend && uv lock && cd ..

# 3. Start everything (builds images, runs migrations automatically)
make up
# or: docker compose up -d --build

# 4. Install frontend deps (local dev only)
cd frontend && pnpm install

# 5. Ingest guidelines (place PDFs in ./guidelines/WHO/, ./guidelines/NICE/, ./guidelines/CDC/)
make ingest-all
```

Frontend: http://localhost:3000  
Backend API docs: http://localhost:8000/docs *(dev only)*

## uv Workflow

```bash
# Sync local dev environment
make uv-sync

# Add a production dependency
make uv-add PKG=httpx

# Regenerate lockfile after pyproject.toml changes
make uv-lock

# Run commands in the managed venv
cd backend && uv run pytest tests/
cd backend && uv run alembic upgrade head
```

## Common Commands

```bash
make test            # Run 103 backend tests
make test-cov        # With HTML coverage report
make lint            # Ruff lint + autofix
make typecheck-backend  # mypy strict
make typecheck-frontend # tsc --noEmit
make migrate         # Apply Alembic migrations
make migrate-rollback   # Roll back one migration
make logs-backend    # Tail backend logs
make shell-backend   # Shell into backend container
make db-studio       # Drizzle Studio (BFF schema)
make prod-up         # Production stack
make reset           # Full teardown + rebuild (destroys data)
```

## Architecture

### Streaming Flow

```
Browser → POST /api/triage (Next.js BFF)
  → POST /v1/triage (FastAPI)
    → Token gate (tiktoken ≤400 tokens)
    → Input restrictions (sanitizer + topic classifier)
    → pgvector RAG (MMR + 0.72 similarity gate)
    → LLM stream (gpt-4o-mini fine-tune) → token_events[] buffered server-side
    → Output restrictions on complete buffer (regex + LLM judge)
    → Replay token_events to client (instant — already buffered)
    → Persist both turns to DB
    → Emit result SSE event with full TriageResponse
  ← SSE stream: token events → result event → [DONE]
← Client renders streaming text, then full response with citations
```

### Restriction Pipeline (7 layers, first failure short-circuits)

| # | Layer | Trigger | Code |
|---|---|---|---|
| 1 | Input sanitizer | Injection patterns, control chars, oversized | RESTRICTION_001 |
| 2 | Topic classifier | Cosine < 0.60 vs medical centroids | RESTRICTION_002 |
| 3 | RAG similarity gate | No chunks above 0.72 cosine | RESTRICTION_003 |
| 4 | Diagnosis language | "you have X" — regex + gpt-4o judge | RESTRICTION_004 |
| 5 | Drug dosage | Specific mg/ml/mcg amounts | RESTRICTION_005 |
| 6 | Certainty language | "definitely", "certainly", "100%" | RESTRICTION_006 |
| 7 | Escalation detector | Red-flag symptom combos | RESTRICTION_007 |

### Auth Flow

```
Register → bcrypt(password) stored, no raw password ever persisted
Login    → always runs bcrypt (even for unknown emails — prevents timing oracle)
         → access_token (JWT, 60min) + refresh_token (SHA-256 hash stored, httpOnly cookie, 30d)
Refresh  → rotate: revoke old token + issue new in one transaction
         → deduplication: concurrent refreshes share one Promise
Logout   → revoke refresh token + clear cookie
```

## Docker Images

| Image | Base | Built with |
|---|---|---|
| `backend` | python:3.12-slim | uv, multi-stage, non-root |
| `celery_worker` | python:3.12-slim | uv, same venv as backend |
| `frontend` | node:22-alpine | pnpm, standalone output, non-root |

```bash
# Build individually
docker build -f backend/Dockerfile backend/ -t triage-backend
docker build -f backend/Dockerfile.celery backend/ -t triage-celery
docker build -f frontend/Dockerfile frontend/ -t triage-frontend
```

## Compliance

- No PHI stored — messages are session-scoped and ephemeral by default  
- Every response has a non-dismissable disclaimer  
- LLM completions traced in Langfuse with `session_id`  
- Rate limited: 20 req / 10 min per token + 80 req / 10 min per IP  
- `triage_messages` is INSERT-only at DB role level (`triage_app_role`)  
- Refresh tokens stored as SHA-256 hashes — raw value never in DB  
- Access token in Zustand memory only — never `localStorage`
