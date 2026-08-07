.PHONY: help up down build logs shell-backend shell-db test lint typecheck migrate \
        ingest-all uv-lock uv-sync clean reset prod-up prod-down

# Default: show help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Docker ─────────────────────────────────────────────────────────────────────
up: ## Start all services (dev)
	docker compose up -d --build
	@echo "\nFrontend: http://localhost:3000"
	@echo "Backend:  http://localhost:8000/docs"

down: ## Stop all services
	docker compose down

build: ## Rebuild all images without cache
	docker compose build --no-cache

logs: ## Tail logs for all services
	docker compose logs -f

logs-backend: ## Tail backend logs only
	docker compose logs -f backend

logs-worker: ## Tail celery worker logs
	docker compose logs -f celery_worker

shell-backend: ## Open a shell in the backend container
	docker compose exec backend bash

shell-db: ## Open psql in the postgres container
	docker compose exec postgres psql -U $${POSTGRES_USER:-triage_user} -d $${POSTGRES_DB:-triage_db}

# ── uv ─────────────────────────────────────────────────────────────────────────
uv-lock: ## Regenerate uv.lock from pyproject.toml
	cd backend && uv lock

uv-sync: ## Sync dev deps into local .venv (outside Docker)
	cd backend && uv sync --dev

uv-add: ## Add a package: make uv-add PKG=httpx
	cd backend && uv add $(PKG)

# ── Migrations ─────────────────────────────────────────────────────────────────
migrate: ## Run Alembic migrations (head)
	docker compose exec backend alembic upgrade head

migrate-status: ## Show current migration revision
	docker compose exec backend alembic current

migrate-history: ## Show migration history
	docker compose exec backend alembic history --verbose

migrate-rollback: ## Roll back one migration
	docker compose exec backend alembic downgrade -1

# ── Testing ───────────────────────────────────────────────────────────────────
test: ## Run backend tests
	docker compose exec backend pytest tests/ -v --tb=short

test-cov: ## Run backend tests with coverage report
	docker compose exec backend pytest tests/ --cov=app --cov-report=html --cov-report=term-missing

test-fast: ## Run tests without slow integration tests
	docker compose exec backend pytest tests/ -v --tb=short -m "not slow"

# ── Lint / Type-check ──────────────────────────────────────────────────────────
lint: ## Lint backend with ruff
	cd backend && uv run ruff check app/ tests/

lint-fix: ## Auto-fix backend lint issues
	cd backend && uv run ruff check --fix app/ tests/

typecheck-backend: ## Type-check backend with mypy
	cd backend && uv run mypy app/

typecheck-frontend: ## Type-check frontend with tsc
	cd frontend && pnpm typecheck

# ── Data ──────────────────────────────────────────────────────────────────────
ingest-all: ## Ingest all guidelines from ./guidelines/ via Celery
	docker compose exec backend python -m app.workers.ingest_cli --all

# ── Drizzle ───────────────────────────────────────────────────────────────────
db-push: ## Push Drizzle schema to DB
	cd frontend && pnpm db:push

db-studio: ## Open Drizzle Studio
	cd frontend && pnpm db:studio

# ── Production ───────────────────────────────────────────────────────────────
prod-up: ## Start production stack
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

prod-down: ## Stop production stack
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# ── Housekeeping ──────────────────────────────────────────────────────────────
clean: ## Remove stopped containers and dangling images
	docker compose down --remove-orphans
	docker image prune -f

reset: ## Full reset — remove volumes and rebuild (DESTROYS DATA)
	@echo "WARNING: This will destroy all data. Press Ctrl+C to cancel."
	@sleep 3
	docker compose down -v --remove-orphans
	docker compose up -d --build
