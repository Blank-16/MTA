import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.api.deps import DbConn, OptionalUser
from app.models.triage import SessionCreateRequest, SessionResponse

logger = logging.getLogger(__name__)
router = APIRouter()



@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(request: SessionCreateRequest, db: DbConn, user: OptionalUser) -> SessionResponse:
    session_id = uuid.uuid4()
    session_token = secrets.token_urlsafe(32)
    user_id = str(request.user_id) if request.user_id else (user.sub if user else None)

    try:
        await db.execute(
            "INSERT INTO triage_sessions (id, session_token, user_id, created_at) VALUES (%s, %s, %s, %s)",
            (str(session_id), session_token, user_id, datetime.now(UTC)),
        )
        await db.commit()
    except Exception as exc:
        logger.error("Failed to create session: %s", exc, exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session creation failed")

    logger.info("Session created id=%s user=%s", session_id, user_id or "anonymous")
    return SessionResponse(session_id=session_id, session_token=session_token)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    db: DbConn,
    user: OptionalUser,
    x_session_token: Annotated[str | None, Header(alias="x-session-token")] = None,
) -> dict:
    if not x_session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="x-session-token required")

    async with await db.execute(
        "SELECT id, created_at, escalated, escalation_reason, restriction_hits FROM triage_sessions WHERE id = %s AND session_token = %s",
        (str(session_id), x_session_token),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return dict(row)


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: uuid.UUID,
    db: DbConn,
    x_session_token: Annotated[str | None, Header(alias="x-session-token")] = None,
) -> list[dict]:
    # FIX: ownership check — verify token before returning any messages
    if not x_session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="x-session-token required")

    async with await db.execute(
        "SELECT id FROM triage_sessions WHERE id = %s AND session_token = %s",
        (str(session_id), x_session_token),
    ) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    async with await db.execute(
        "SELECT id, role, content, citations, confidence, restriction_log, created_at FROM triage_messages WHERE session_id = %s ORDER BY created_at ASC",
        (str(session_id),),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def end_session(
    session_id: uuid.UUID,
    db: DbConn,
    x_session_token: Annotated[str | None, Header(alias="x-session-token")] = None,
) -> None:
    # FIX: only session owner can close their session
    if not x_session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="x-session-token required")

    try:
        await db.execute(
            "UPDATE triage_sessions SET ended_at = %s WHERE id = %s AND session_token = %s AND ended_at IS NULL",
            (datetime.now(UTC), str(session_id), x_session_token),
        )
        await db.commit()
    except Exception as exc:
        logger.error("Failed to end session %s: %s", session_id, exc, exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to end session")


@router.get("/sessions")
async def list_user_sessions(
    db: DbConn,
    user: OptionalUser,
    x_session_token: Annotated[str | None, Header(alias="x-session-token")] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """
    Returns sessions belonging to the authenticated user, or the single session
    matching the provided session token for anonymous users.
    """
    if user:
        async with await db.execute(
            """
            SELECT id, created_at, escalated, escalation_reason
            FROM triage_sessions
            WHERE user_id = %s AND ended_at IS NULL
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (user.sub, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
    elif x_session_token:
        async with await db.execute(
            """
            SELECT id, created_at, escalated, escalation_reason
            FROM triage_sessions
            WHERE session_token = %s AND ended_at IS NULL
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (x_session_token, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
    else:
        return []

    return [dict(r) for r in rows]
