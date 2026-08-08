import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import DbConn, OptionalUser
from app.core.config import settings
from app.core.database import acquire
from app.core.token_counter import count_tokens
from app.models.triage import Citation, TriageRequest, TriageResponse
from app.services.llm.chain import (
    _stream_buffers,
    build_triage_chain,
    format_context,
    format_history,
    run_chain_with_streaming,
)
from app.services.rag.retriever import ClinicalRetriever
from app.services.restrictions.escalation_detector import EscalationDetector
from app.services.restrictions.input_sanitizer import InputSanitizer
from app.services.restrictions.output_validator import OutputValidator
from app.services.restrictions.pipeline import RestrictionCode, RestrictionPipeline
from app.services.restrictions.topic_classifier import TopicClassifier

logger = logging.getLogger(__name__)
router = APIRouter()

_RESTRICTION_HTTP_CODES: dict[RestrictionCode, int] = {
    RestrictionCode.PROMPT_INJECTION:   status.HTTP_422_UNPROCESSABLE_ENTITY,
    RestrictionCode.OFF_TOPIC:          status.HTTP_422_UNPROCESSABLE_ENTITY,
    RestrictionCode.LOW_SIMILARITY:     status.HTTP_422_UNPROCESSABLE_ENTITY,
    RestrictionCode.DIAGNOSIS_LANGUAGE: status.HTTP_422_UNPROCESSABLE_ENTITY,
    RestrictionCode.DRUG_DOSAGE:        status.HTTP_422_UNPROCESSABLE_ENTITY,
    RestrictionCode.HIGH_CERTAINTY:     status.HTTP_422_UNPROCESSABLE_ENTITY,
    RestrictionCode.ESCALATION_TRIGGER: status.HTTP_200_OK,
}

_SAFE_MESSAGES: dict[RestrictionCode, str] = {
    RestrictionCode.PROMPT_INJECTION:   "Your message could not be processed. Please rephrase and try again.",
    RestrictionCode.OFF_TOPIC:          "This assistant only handles medical and health-related queries.",
    RestrictionCode.LOW_SIMILARITY:     "No matching clinical guidelines found. Please consult a healthcare provider.",
    RestrictionCode.DIAGNOSIS_LANGUAGE: "A response could not be generated safely. Please consult a healthcare provider.",
    RestrictionCode.DRUG_DOSAGE:        "A response could not be generated safely. Please consult a pharmacist.",
    RestrictionCode.HIGH_CERTAINTY:     "A response could not be generated safely. Please consult a healthcare provider.",
    RestrictionCode.ESCALATION_TRIGGER: "Based on your symptoms, please seek immediate medical attention.",
}

_escalation_detector = EscalationDetector()
_pipeline = RestrictionPipeline(
    sanitizer=InputSanitizer(),
    classifier=TopicClassifier(),
    output_validator=OutputValidator(),
    escalation_detector=_escalation_detector,
)
_chain = build_triage_chain()
_retriever: ClinicalRetriever | None = None
_retriever_lock = asyncio.Lock()


async def _get_retriever() -> ClinicalRetriever:
    global _retriever
    if _retriever is not None:
        return _retriever
    async with _retriever_lock:
        if _retriever is None:
            _retriever = ClinicalRetriever(connection_string=settings.psycopg_conninfo)
    return _retriever


async def _verify_session_ownership(db: DbConn, session_id: uuid.UUID, session_token: str) -> None:
    async with await db.execute(
        "SELECT id FROM triage_sessions WHERE id = %s AND session_token = %s AND ended_at IS NULL",
        (str(session_id), session_token),
    ) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired session")


async def _load_conversation_history(
    db: DbConn,
    session_id: uuid.UUID,
    max_turns: int,
) -> list[dict[str, str]]:
    """
    Loads the last max_turns message pairs from the session.
    Returns [{"role": "user"|"assistant", "content": "..."}] ordered oldest-first.
    """
    async with await db.execute(
        """
        SELECT role, content
        FROM triage_messages
        WHERE session_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (str(session_id), max_turns * 2),
    ) as cur:
        rows = await cur.fetchall()

    # Reverse so oldest is first
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def _sse_error(code: RestrictionCode, http_status: int) -> StreamingResponse:
    """Returns a StreamingResponse that emits a single error SSE event."""
    msg = _SAFE_MESSAGES.get(code, "Request could not be processed.")
    payload = json.dumps({"type": "error", "code": str(code), "detail": msg})

    async def _gen():
        yield f"data: {payload}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _gen(),
        status_code=http_status,
        media_type="text/event-stream",
    )


@router.post("/triage")
async def triage(
    request: TriageRequest,
    db: DbConn,
    user: OptionalUser,
    x_session_token: Annotated[str | None, Header(alias="x-session-token")] = None,
) -> StreamingResponse:
    if not x_session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="x-session-token header required")

    log_ctx = {"session_id": str(request.session_id), "user_id": user.sub if user else "anonymous"}
    logger.info("Triage request received", extra=log_ctx)

    await _verify_session_ownership(db, request.session_id, x_session_token)

    # Token gate — reject before any LLM or embedding cost
    token_count = count_tokens(request.message)
    if token_count > settings.max_input_tokens:
        logger.warning("Input token gate triggered count=%d max=%d", token_count, settings.max_input_tokens)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Input too long ({token_count} tokens). Please shorten your message.",
        )

    # Pre-LLM escalation check
    pre_escalation = _escalation_detector.detect_in_user_input(request.message)
    if not pre_escalation.passed:
        logger.info("Pre-LLM escalation: %s", pre_escalation.reason, extra=log_ctx)
        msg_id = uuid.uuid4()
        response = TriageResponse(
            session_id=request.session_id,
            message_id=msg_id,
            summary=_SAFE_MESSAGES[RestrictionCode.ESCALATION_TRIGGER],
            citations=[],
            escalate=True,
            escalation_reason=pre_escalation.reason,
            confidence="high",
            disclaimer="emergency",
            restriction_triggered=True,
            restriction_code=str(RestrictionCode.ESCALATION_TRIGGER),
        )
        async with acquire() as fresh_db:
            await _persist_turn(fresh_db, request, response, msg_id)
        return _stream_complete_response(response)

    # Input restriction layers 1 + 2
    input_result = await _pipeline.run_input(request.message)
    if not input_result.passed:
        logger.warning("Input restriction code=%s", input_result.code, extra=log_ctx)
        return _sse_error(
            input_result.code,
            _RESTRICTION_HTTP_CODES.get(input_result.code, 422),
        )

    # RAG retrieval (layer 3 gate)
    chunks = await (await _get_retriever()).retrieve(request.message)
    if not chunks:
        logger.warning("RAG similarity gate: no chunks above threshold", extra=log_ctx)
        return _sse_error(RestrictionCode.LOW_SIMILARITY, status.HTTP_422_UNPROCESSABLE_ENTITY)

    # Load conversation history for multi-turn context
    history_turns = await _load_conversation_history(db, request.session_id, settings.max_context_turns)
    history_text = format_history(history_turns)

    context_text = format_context(chunks)

    return StreamingResponse(
        _stream_triage(
            request=request,
            context=context_text,
            history=history_text,
            chunks=chunks,
            log_ctx=log_ctx,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def _stream_triage(
    request: TriageRequest,
    context: str,
    history: str,
    chunks: list,
    log_ctx: dict,
) -> AsyncGenerator[str, None]:
    """
    Core streaming generator.
    DB connection is acquired fresh inside the generator — not passed from the route handler.
    The route handler's DbConn dependency is scoped to the route lifetime and would be
    returned to the pool before the generator finishes streaming.
    """
    session_key = str(request.session_id)
    buffer_key: str | None = None

    try:
        # Phase 1: collect all events server-side — do NOT yield tokens to client yet.
        # The buffer/replay strategy requires restriction checks to complete before
        # any content is sent. Forwarding tokens before validation allows unsafe
        # content to reach the client if restrictions fire on later parts of the response.
        token_events: list[str] = []
        async for event in run_chain_with_streaming(
            context=context,
            question=request.message,
            history=history,
            session_id=session_key,
        ):
            try:
                data = json.loads(event.replace("data: ", "").strip())
            except json.JSONDecodeError:
                logger.warning("Malformed SSE event from chain: %r", event[:100])
                continue
            if data["type"] == "error":
                yield event
                yield "data: [DONE]\n\n"
                return
            if data["type"] == "buffer_complete":
                buffer_key = data.get("key")
                break
            if data["type"] == "token":
                # Buffer server-side — replay only after validation
                token_events.append(event)

        # Phase 2: retrieve buffer out-of-band (no SSE line size limit)
        buffer = _stream_buffers.pop(buffer_key, "") if buffer_key else ""
        if not buffer:
            logger.error("Empty buffer after streaming — LLM produced no output", extra=log_ctx)
            yield f"data: {json.dumps({'type': 'error', 'detail': 'LLM produced no response.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Phase 3: output restriction checks on complete buffer
        chunk_texts = [c["content"] for c in chunks]
        output_result = await _pipeline.run_output(buffer, chunk_texts)
        if not output_result.passed and output_result.code != RestrictionCode.ESCALATION_TRIGGER:
            logger.warning("Output restriction code=%s", output_result.code, extra=log_ctx)
            yield f"data: {json.dumps({'type': 'error', 'code': str(output_result.code), 'detail': _SAFE_MESSAGES.get(output_result.code, 'Response blocked.')})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Phase 4: parse full JSON
        try:
            raw: dict = json.loads(buffer)
        except json.JSONDecodeError as exc:
            logger.error("LLM returned invalid JSON: %s", exc, extra=log_ctx)
            yield f"data: {json.dumps({'type': 'error', 'detail': 'LLM returned an invalid response.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        escalate: bool = raw.get("escalate", False) or (
            not output_result.passed and output_result.code == RestrictionCode.ESCALATION_TRIGGER
        )

        summary: str = raw.get("summary", "")
        raw_citations: list[dict] = raw.get("citations") or [
            {"source": c["source"], "section": c["section"],
             "similarity": c["similarity"], "jurisdiction": c["jurisdiction"]}
            for c in chunks[:3]
        ]
        citations = [
            Citation(
                source=c.get("source", "unknown"),
                section=c.get("section", ""),
                similarity=float(c.get("similarity", 0.0)),
                jurisdiction=c.get("jurisdiction", "global"),
            )
            for c in raw_citations
        ]
        msg_id = uuid.uuid4()
        response = TriageResponse(
            session_id=request.session_id,
            message_id=msg_id,
            summary=summary,
            citations=citations,
            escalate=escalate,
            escalation_reason=raw.get("escalation_reason") or (output_result.reason if escalate else None),
            confidence=raw.get("confidence", "moderate"),
            disclaimer="emergency" if escalate else raw.get("disclaimer", "consult_gp"),
            restriction_triggered=not output_result.passed,
            restriction_code=str(output_result.code) if not output_result.passed else None,
        )

        # Yield result to client BEFORE the DB write — DB latency must not delay
        # the user receiving their response. Persist is a background concern.
        yield f"data: {json.dumps({'type': 'result', 'data': response.model_dump(mode='json')})}\n\n"
        yield "data: [DONE]\n\n"

        logger.info("Triage stream complete escalate=%s confidence=%s", escalate, response.confidence, extra=log_ctx)

        # Persist after client receives response — non-blocking from client perspective
        async with acquire() as fresh_db:
            await _persist_turn(fresh_db, request, response, msg_id)

    except Exception as exc:
        # Outer catch — unhandled exception after first yield sends a clean error event
        # instead of silently closing the stream mid-message.
        logger.error("Unhandled error in _stream_triage: %s", exc, exc_info=True, extra=log_ctx)
        _stream_buffers.pop(buffer_key, None) if buffer_key else None  # clean up dangling buffer
        try:
            yield f"data: {json.dumps({'type': 'error', 'detail': 'An unexpected error occurred.'})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            pass  # generator already closed



def _stream_complete_response(response: TriageResponse) -> StreamingResponse:
    """Wraps a pre-built TriageResponse as a single-event SSE stream (for escalation fast-path)."""
    payload = json.dumps({"type": "result", "data": response.model_dump(mode="json")})

    async def _gen():
        yield f"data: {payload}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store"})


async def _persist_turn(
    db: DbConn,
    request: TriageRequest,
    response: TriageResponse,
    message_id: uuid.UUID,
) -> None:
    now = datetime.now(UTC)
    user_msg_id = uuid.uuid4()
    try:
        await db.execute(
            "INSERT INTO triage_messages (id, session_id, role, content, citations, confidence, restriction_log, created_at) VALUES (%s, %s, 'user', %s, '[]'::jsonb, NULL, '{}'::jsonb, %s)",
            (str(user_msg_id), str(request.session_id), request.message, now),
        )
        await db.execute(
            "INSERT INTO triage_messages (id, session_id, role, content, citations, confidence, model_version, restriction_log, created_at) VALUES (%s, %s, 'assistant', %s, %s::jsonb, %s, %s, %s::jsonb, %s)",
            (
                str(message_id), str(request.session_id), response.summary,
                json.dumps([c.model_dump() for c in response.citations]),
                response.confidence, settings.fine_tuned_model_id,
                json.dumps({"restriction_triggered": response.restriction_triggered,
                            "restriction_code": response.restriction_code,
                            "escalated": response.escalate}),
                now,
            ),
        )
        if response.escalate:
            await db.execute(
                "UPDATE triage_sessions SET escalated = TRUE, escalation_reason = %s WHERE id = %s",
                (response.escalation_reason, str(request.session_id)),
            )
        await db.commit()
    except Exception as exc:
        logger.error("Audit write failed (non-fatal): %s", exc, exc_info=True)
        await db.rollback()
