import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.v1 import admin, auth, sessions, triage

# All imports before app construction
from app.core.config import settings
from app.core.database import close_pool, health_check, init_pool
from app.core.logging_config import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.core.rate_limiter import sliding_window_rate_limit
from app.core.redis_client import close_redis, init_redis, redis_health_check
from app.core.telemetry import configure_otel

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup env=%s log_level=%s", settings.environment, settings.log_level)
    await init_pool()
    await init_redis()
    yield
    logger.info("Shutdown initiated")
    await close_pool()
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Medical Triage Assistant API",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

configure_otel(app)

# Middleware registered in reverse call order (outermost first)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        ["http://localhost:3000"] if not settings.is_production else []
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "x-session-token", "x-internal-key", "x-request-id"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)


@app.exception_handler(ValidationError)
async def _pydantic_handler(request: Request, exc: ValidationError) -> JSONResponse:
    logger.warning(
        "Validation error path=%s errors=%d request_id=%s",
        request.url.path,
        exc.error_count(),
        getattr(request.state, "request_id", "-"),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(include_url=False)},
    )


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception path=%s request_id=%s",
        request.url.path,
        getattr(request.state, "request_id", "-"),
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@app.get("/health", tags=["ops"], include_in_schema=False)
async def health() -> Any:
    db_ok = await health_check()
    redis_ok = await redis_health_check()
    healthy = db_ok and redis_ok
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ok" if healthy else "degraded",
            "environment": settings.environment,
            "checks": {
                "database": "ok" if db_ok else "error",
                "redis": "ok" if redis_ok else "error",
            },
        },
    )


app.include_router(
    triage.router,
    prefix="/v1",
    tags=["triage"],
    dependencies=[Depends(sliding_window_rate_limit)],
)
app.include_router(sessions.router, prefix="/v1", tags=["sessions"])
app.include_router(auth.router, prefix="/v1", tags=["auth"])
app.include_router(admin.router, prefix="/v1", tags=["admin"])
