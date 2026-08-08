# syntax=docker/dockerfile:1.7
#
# Multi-stage build using uv for fast, reproducible dependency installation.
# Stages: uv → deps (install) → runtime (minimal image)
#
# uv benefits over pip:
#   - 10-100x faster resolution and installation
#   - Reproducible via uv.lock (like npm lockfile)
#   - No need for virtualenv activation — PATH points at .venv/bin

# ── Stage 1: uv binary ───────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:0.4.20 AS uv

# ── Stage 2: install dependencies ────────────────────────────────────────────
FROM python:3.12-slim AS deps

WORKDIR /app

# Build-time system deps (psycopg binary, bcrypt C extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

# uv binary from stage 1
COPY --from=uv /uv /usr/local/bin/uv

ENV UV_CACHE_DIR=/root/.cache/uv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Copy only manifests first — Docker layer cache: dep changes rarely
COPY pyproject.toml uv.lock* ./

# Install into /app/.venv — BuildKit cache mount skips re-downloading on rebuild
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable 2>/dev/null || \
    uv sync --no-dev --no-editable

# ── Stage 3: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# libpq5 at runtime, curl for HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

# Non-root user
RUN addgroup --system app && adduser --system --ingroup app --no-create-home app

# Copy venv from deps stage — not the entire Python installation
COPY --from=deps --chown=app:app /app/.venv /app/.venv

# Copy source last — most frequently changed layer
COPY --chown=app:app . .

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -sf http://localhost:8000/health | python3 -c \
        "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)"

# uvloop + httptools: significantly faster than default asyncio event loop and HTTP parser
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--access-log"]
