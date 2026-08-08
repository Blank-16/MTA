import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbConn, InternalRoute

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/admin/audit", dependencies=[InternalRoute])
async def list_audit_entries(
    db: DbConn,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    escalated_only: bool = Query(default=False),
) -> list[dict]:
    # FIX: use parameterised query instead of str.format() — eliminates injection pattern
    # psycopg doesn't support dynamic WHERE with %s for clause presence,
    # so we use two separate queries rather than string-building.
    if escalated_only:
        query = """
            SELECT
                m.id, m.session_id, m.role, m.confidence,
                m.restriction_log, m.created_at,
                s.escalated, s.escalation_reason
            FROM triage_messages m
            JOIN triage_sessions s ON m.session_id = s.id
            WHERE s.escalated = TRUE
            ORDER BY m.created_at DESC
            LIMIT %s OFFSET %s
        """
    else:
        query = """
            SELECT
                m.id, m.session_id, m.role, m.confidence,
                m.restriction_log, m.created_at,
                s.escalated, s.escalation_reason
            FROM triage_messages m
            JOIN triage_sessions s ON m.session_id = s.id
            ORDER BY m.created_at DESC
            LIMIT %s OFFSET %s
        """

    async with await db.execute(query, (limit, offset)) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/admin/restrictions/stats", dependencies=[InternalRoute])
async def restriction_stats(db: DbConn) -> dict:
    async with await db.execute(
        """
        SELECT
            restriction_log->>'restriction_code' AS code,
            COUNT(*) AS count
        FROM triage_messages
        WHERE restriction_log->>'restriction_triggered' = 'true'
        GROUP BY code
        ORDER BY count DESC
        """
    ) as cur:
        rows = await cur.fetchall()
    return {"stats": [dict(r) for r in rows]}


@router.get("/admin/sessions/stats", dependencies=[InternalRoute])
async def session_stats(db: DbConn) -> dict:
    async with await db.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE escalated = TRUE)  AS escalated_count,
            COUNT(*) FILTER (WHERE ended_at IS NULL)  AS active_count,
            COUNT(*)                                   AS total_count,
            AVG(EXTRACT(EPOCH FROM (ended_at - created_at)))
                FILTER (WHERE ended_at IS NOT NULL)   AS avg_session_duration_seconds
        FROM triage_sessions
        """
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else {}


@router.post("/admin/guidelines/ingest", dependencies=[InternalRoute], status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingestion(source: str) -> dict:
    try:
        from app.workers.ingestion_worker import ingest_task
        task = ingest_task.delay(source)
        logger.info("Ingestion task dispatched source=%s task_id=%s", source, task.id)
        return {"task_id": task.id, "status": "queued"}
    except Exception as exc:
        logger.error("Failed to dispatch ingestion task: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue ingestion",
        )
