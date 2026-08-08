import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None


async def init_pool() -> None:
    global _pool
    if _pool is not None:
        logger.warning("init_pool called but pool already exists — skipping")
        return

    logger.info("Initialising DB pool min=%d max=%d", settings.db_pool_min_size, settings.db_pool_max_size)
    _pool = AsyncConnectionPool(
        conninfo=settings.psycopg_conninfo,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        max_waiting=settings.db_pool_max_waiting,
        max_idle=settings.db_pool_max_idle,
        kwargs={"row_factory": dict_row, "autocommit": False},
        open=False,
    )
    try:
        await _pool.open(wait=True, timeout=10.0)
    except Exception as exc:
        logger.critical("DB pool failed to open: %s", exc, exc_info=True)
        raise
    logger.info("DB pool ready")


async def close_pool() -> None:
    global _pool
    if _pool is None:
        return
    logger.info("Closing DB pool")
    try:
        await _pool.close(timeout=5.0)
    except Exception as exc:
        logger.error("Error closing DB pool: %s", exc, exc_info=True)
    finally:
        _pool = None


def _require_pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError(
            "Database pool is not initialised. "
            "Ensure init_pool() is called during application startup."
        )
    return _pool


@asynccontextmanager
async def acquire() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    pool = _require_pool()
    async with pool.connection() as conn:
        try:
            yield conn
        except Exception:
            await conn.rollback()
            raise


async def get_db() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    async with acquire() as conn:
        yield conn


async def health_check() -> bool:
    try:
        async with acquire() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as exc:
        logger.error("DB health check failed: %s", exc)
        return False
