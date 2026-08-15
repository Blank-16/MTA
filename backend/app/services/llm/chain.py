import json
import logging
import threading
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# Out-of-band buffer store: nonce_key → (buffer_text, inserted_at)
# Callers pop their key immediately. Keys that linger > 120s (client disconnect
# before the generator reads them) are pruned by _prune_stale_buffers().
_stream_buffers: dict[str, tuple[str, float]] = {}
_BUFFER_TTL_SECONDS = 120


def _prune_stale_buffers() -> None:
    """Remove buffer entries older than TTL. Called on each new streaming request."""
    cutoff = time.monotonic() - _BUFFER_TTL_SECONDS
    stale = [k for k, (_, ts) in _stream_buffers.items() if ts < cutoff]
    for k in stale:
        logger.warning("Pruning stale stream buffer key=%s", k[:8])
        _stream_buffers.pop(k, None)

_SYSTEM_PROMPT = """You are a medical triage assistant. Strict rules:

1. Ground EVERY claim exclusively in the provided clinical guideline excerpts.
2. NEVER diagnose, prescribe, or state drug dosages.
3. NEVER use certainty phrases: "you have", "this is", "definitely", "certainly".
4. ALWAYS cite the guideline source and section for every factual claim.
5. If symptoms suggest emergency, set escalate=true and disclaimer=emergency.
6. Return ONLY valid JSON matching this exact schema — no prose outside JSON:

{{
  "summary": "string — general information grounded in guidelines",
  "citations": [{{"source": "string", "section": "string", "similarity": float, "jurisdiction": "string"}}],
  "escalate": boolean,
  "escalation_reason": "string or null",
  "confidence": "high | moderate | low",
  "disclaimer": "consult_gp | emergency | pharmacist",
  "restriction_triggered": false,
  "restriction_code": null
}}"""


def _get_langfuse_callback():
    try:
        from langfuse.callback import CallbackHandler
        handler = CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.debug("Langfuse callback handler initialised")
        return handler
    except Exception as exc:
        logger.warning("Langfuse init failed — tracing disabled: %s", exc)
        return None


_langfuse_handler = _get_langfuse_callback()

# Module-level LLM instances — construction is not free; reuse across requests
_llm_non_streaming: ChatOpenAI | None = None
_llm_streaming: ChatOpenAI | None = None
_llm_lock = threading.Lock()
# Module-level prompt — immutable, safe to share across all requests
_TRIAGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_PROMPT),
    ("human", "Clinical guideline excerpts:\n{context}\n\nConversation history:\n{history}\n\nPatient message:\n{question}"),
])


def _get_llm(streaming: bool = False) -> ChatOpenAI:
    global _llm_non_streaming, _llm_streaming
    if streaming:
        if _llm_streaming is not None:
            return _llm_streaming
        with _llm_lock:
            if _llm_streaming is None:
                _llm_streaming = ChatOpenAI(
                    model=settings.fine_tuned_model_id,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                    openai_api_key=settings.openai_api_key,
                    streaming=True,
                )
        return _llm_streaming
    if _llm_non_streaming is not None:
        return _llm_non_streaming
    with _llm_lock:
        if _llm_non_streaming is None:
            _llm_non_streaming = ChatOpenAI(
                model=settings.fine_tuned_model_id,
                temperature=0.1,
                response_format={"type": "json_object"},
                openai_api_key=settings.openai_api_key,
                streaming=False,
            )
    return _llm_non_streaming


def build_triage_chain() -> Runnable:
    return (
        RunnablePassthrough.assign(context=lambda x: x["context"])
        | _TRIAGE_PROMPT
        | _get_llm(streaming=False)
        | JsonOutputParser()
    )


def format_context(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[{i}] Source: {chunk.get('source', 'unknown')} — {chunk.get('section', '')}\n"
            f"{chunk.get('content', '')}"
        )
    return "\n\n---\n\n".join(parts)


def format_history(turns: list[dict[str, str]]) -> str:
    """
    Formats prior conversation turns as a readable block for the prompt.
    Keeps the last N turns only — caller is responsible for slicing.
    Returns empty string when turns is empty so the prompt stays clean.
    """
    if not turns:
        return "(no prior conversation)"
    lines = []
    for t in turns:
        role = "Patient" if t["role"] == "user" else "Assistant"
        lines.append(f"{role}: {t['content']}")
    return "\n".join(lines)


async def run_chain_with_streaming(
    context: str,
    question: str,
    history: str,
    session_id: str,
) -> AsyncGenerator[str, None]:
    """
    Streams raw JSON tokens from the LLM as SSE-compatible lines.

    Buffer stored out-of-band in _stream_buffers keyed on a per-request UUID nonce
    (not session_id) — prevents concurrent requests on the same session from
    overwriting each other's buffer.

    The nonce is emitted in the buffer_complete event so the caller can retrieve it.
    """
    # Per-request nonce prevents buffer collision when two requests share the same session_id
    buffer_key = str(uuid.uuid4())

    llm = _get_llm(streaming=True)
    invoke_config = get_langfuse_config(session_id)
    messages = await _TRIAGE_PROMPT.aformat_messages(context=context, history=history, question=question)

    buffer = ""
    try:
        async for chunk in llm.astream(messages, config=invoke_config):  # type: ignore
            if chunk.content:
                buffer += chunk.content  # type: ignore
                yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"
    except Exception as exc:
        logger.error("LLM stream failed session=%s: %s", session_id, exc, exc_info=True)
        # No buffer to clean up — key never written on exception before buffer_complete
        yield f"data: {json.dumps({'type': 'error', 'detail': 'LLM stream failed'})}\n\n"
        return

    # Store out-of-band with timestamp for TTL pruning
    _prune_stale_buffers()  # cheap O(n) scan on each request — n is tiny in practice
    _stream_buffers[buffer_key] = (buffer, time.monotonic())
    yield f"data: {json.dumps({'type': 'buffer_complete', 'key': buffer_key})}\n\n"


def get_langfuse_config(session_id: str) -> dict[str, Any]:
    if _langfuse_handler is None:
        return {}
    return {
        "callbacks": [_langfuse_handler],
        "metadata": {"session_id": session_id},
        "run_name": "triage_chain",
        "tags": ["triage", settings.environment],
    }
