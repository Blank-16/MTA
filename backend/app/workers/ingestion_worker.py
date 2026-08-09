import asyncio
import logging

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "triage_worker",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # Requeue on worker crash
    worker_prefetch_multiplier=1,
    result_expires=3600,  # Purge task results from Redis after 1h — prevents unbounded growth
)


@celery_app.task(bind=True, name="ingest_task", max_retries=3, default_retry_delay=60)
def ingest_task(self, source: str) -> dict:
    """
    Wraps async ingestion in sync Celery task.
    Retries up to 3 times with 60s delay on transient failures.
    """
    try:
        result = asyncio.run(_run_ingestion(source))
        logger.info("Ingestion complete source=%s chunks=%s", source, result)
        return {"source": source, "chunks_ingested": result}
    except Exception as exc:
        logger.error("Ingestion task failed source=%s: %s", source, exc, exc_info=True)
        raise self.retry(exc=exc)


_ALLOWED_SOURCE_RE = __import__('re').compile(r'^[A-Z]{2,10}$')


async def _run_ingestion(source: str) -> dict:
    import os

    from app.services.rag.ingestion import GuidelineIngestionPipeline

    # Sanitise source — only uppercase alpha, 2-10 chars (e.g. WHO, NICE, CDC)
    if not _ALLOWED_SOURCE_RE.match(source):
        raise ValueError(f"Invalid source name: {source!r}. Must match [A-Z]{{2,10}}.")

    # Resolve to absolute path and verify it stays inside the guidelines directory
    guidelines_root = os.path.realpath("./guidelines")
    target = os.path.realpath(os.path.join(guidelines_root, source))
    if not target.startswith(guidelines_root + os.sep) and target != guidelines_root:
        raise ValueError(f"Path traversal attempt blocked: {source!r}")

    pipeline = GuidelineIngestionPipeline(connection_string=settings.psycopg_conninfo)
    return await pipeline.ingest_all(target)
