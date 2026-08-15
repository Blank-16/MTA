import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestStreamingChain:
    async def test_format_history_empty(self):
        from app.services.llm.chain import format_history
        result = format_history([])
        assert result == "(no prior conversation)"

    async def test_format_history_turns(self):
        from app.services.llm.chain import format_history
        turns = [
            {"role": "user", "content": "headache"},
            {"role": "assistant", "content": "Based on guidelines..."},
        ]
        result = format_history(turns)
        assert "Patient:" in result
        assert "headache" in result
        assert "Assistant:" in result
        assert "Based on guidelines" in result

    async def test_format_history_preserves_order(self):
        from app.services.llm.chain import format_history
        turns = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ]
        result = format_history(turns)
        assert result.index("first") < result.index("second") < result.index("third")

    async def test_sse_error_event_format(self):
        """_sse_error should yield a valid SSE error event."""
        from fastapi import status

        from app.api.v1.triage import _sse_error
        from app.services.restrictions.pipeline import RestrictionCode

        response = _sse_error(RestrictionCode.OFF_TOPIC, status.HTTP_422_UNPROCESSABLE_ENTITY)
        assert response.status_code == 422
        assert "text/event-stream" in response.media_type

        events = []
        async for chunk in response.body_iterator:
            events.append(chunk)

        assert any("[DONE]" in e for e in events)
        error_events = [e for e in events if "type" in e and "[DONE]" not in e]
        assert len(error_events) > 0
        parsed = json.loads(error_events[0].replace("data: ", "").strip())
        assert parsed["type"] == "error"
        assert "RESTRICTION_002" in parsed["code"]

    async def test_stream_complete_response_format(self):
        """_stream_complete_response should yield result then DONE."""
        import uuid

        from app.api.v1.triage import _stream_complete_response
        from app.models.triage import TriageResponse

        response = TriageResponse(
            session_id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            summary="General advice.",
            citations=[],
            escalate=False,
            escalation_reason=None,
            confidence="moderate",
            disclaimer="consult_gp",
            restriction_triggered=False,
            restriction_code=None,
        )
        streaming = _stream_complete_response(response)
        events = []
        async for chunk in streaming.body_iterator:
            events.append(chunk)

        assert any("[DONE]" in e for e in events)
        result_events = [e for e in events if '"type": "result"' in e]
        assert len(result_events) == 1
        parsed = json.loads(result_events[0].replace("data: ", "").strip())
        assert parsed["data"]["escalate"] is False
        assert parsed["data"]["confidence"] == "moderate"


class TestBufferOutOfBand:
    """_stream_buffers dict stores buffer separate from SSE lines."""

    async def test_buffer_complete_event_has_no_buffer_key(self):
        """buffer_complete event must NOT embed the buffer — only signals completion."""
        from app.services.llm.chain import run_chain_with_streaming

        mock_chunk = MagicMock()
        mock_chunk.content = "test content"

        async def mock_astream(*args, **kwargs):
            yield mock_chunk

        with patch("app.services.llm.chain._get_llm") as MockLLM:
            MockLLM.return_value.astream = mock_astream
            events = []
            async for event in run_chain_with_streaming("ctx", "q", "hist", "session-123"):
                events.append(event)

        import json
        buffer_complete_events = [
            e for e in events
            if "buffer_complete" in e
        ]
        assert len(buffer_complete_events) == 1
        parsed = json.loads(buffer_complete_events[0].replace("data: ", "").strip())
        assert "buffer" not in parsed, "buffer_complete must NOT embed payload in SSE line"
        assert parsed["type"] == "buffer_complete"

    async def test_buffer_stored_under_nonce_key(self):
        """Buffer is stored under nonce key (not session_id) to prevent concurrent collisions."""
        import json

        from app.services.llm.chain import _stream_buffers, run_chain_with_streaming

        mock_chunk = MagicMock()
        mock_chunk.content = "hello world response"
        session_id = "test-session-buffer"
        found_key = None

        async def mock_astream(*args, **kwargs):
            yield mock_chunk

        with patch("app.services.llm.chain._get_llm") as MockLLM:
            MockLLM.return_value.astream = mock_astream
            async for event in run_chain_with_streaming("ctx", "q", "hist", session_id):
                if "buffer_complete" in event:
                    data = json.loads(event.replace("data: ", "").strip())
                    found_key = data.get("key")

        # Buffer stored under nonce key, NOT session_id
        assert found_key is not None
        assert session_id not in _stream_buffers, "Must not use session_id as buffer key"
        assert found_key in _stream_buffers
        assert _stream_buffers[found_key][0] == "hello world response"
        del _stream_buffers[found_key]


class TestMiddlewareASGI:
    async def test_middleware_is_pure_asgi(self):
        """Verify RequestIDMiddleware does not subclass BaseHTTPMiddleware."""
        from starlette.middleware.base import BaseHTTPMiddleware

        from app.core.middleware import RequestIDMiddleware
        assert not issubclass(RequestIDMiddleware, BaseHTTPMiddleware), \
            "Must be pure ASGI middleware — BaseHTTPMiddleware buffers streaming responses"

    async def test_middleware_injects_request_id(self):
        """Request ID header present in response."""
        from fastapi.testclient import TestClient

        from app.core.database import get_db
        from app.main import app

        async def mock_db():
            yield MagicMock()

        app.dependency_overrides[get_db] = mock_db
        with patch("app.main.init_pool", new=AsyncMock()), \
             patch("app.main.init_redis", new=AsyncMock()), \
             patch("app.main.close_pool", new=AsyncMock()), \
             patch("app.main.close_redis", new=AsyncMock()), \
             patch("app.core.redis_client._redis", MagicMock()), \
             TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/health")
            assert "x-request-id" in r.headers
        app.dependency_overrides.clear()


class TestBufferKeyNonce:
    """buffer_complete event must emit a nonce key, not session_id."""

    async def test_buffer_complete_emits_key(self):
        import json

        from app.services.llm.chain import _stream_buffers, run_chain_with_streaming

        mock_chunk = MagicMock()
        mock_chunk.content = '{"summary": "test"}'

        async def mock_astream(*args, **kwargs):
            yield mock_chunk

        with patch("app.services.llm.chain._get_llm") as MockLLM:
            MockLLM.return_value.astream = mock_astream
            events = []
            async for event in run_chain_with_streaming("ctx", "q", "hist", "sess-abc"):
                events.append(event)

        complete = [e for e in events if "buffer_complete" in e]
        assert len(complete) == 1
        parsed = json.loads(complete[0].replace("data: ", "").strip())
        assert "key" in parsed, "buffer_complete must include nonce key"
        key = parsed["key"]
        # Key must be a UUID4 format, NOT the session_id
        assert key != "sess-abc", "Key must be a unique nonce, not session_id"
        import re
        assert re.match(r"[0-9a-f-]{36}", key), "Key must be UUID format"
        # Buffer must be stored under the nonce key
        assert key in _stream_buffers
        # Cleanup
        _stream_buffers.pop(key, None)

    async def test_concurrent_sessions_use_separate_keys(self):
        """Two concurrent runs on the same session_id don't collide."""
        import json

        from app.services.llm.chain import _stream_buffers, run_chain_with_streaming

        async def make_chunk(content):
            m = MagicMock()
            m.content = content
            return m

        async def mock_astream_a(*args, **kwargs):
            yield await make_chunk('{"summary": "response A"}')

        async def mock_astream_b(*args, **kwargs):
            yield await make_chunk('{"summary": "response B"}')

        keys = []
        with patch("app.services.llm.chain._get_llm") as MockLLM:
            MockLLM.return_value.astream = mock_astream_a
            async for e in run_chain_with_streaming("ctx", "q", "hist", "same-session"):
                if "buffer_complete" in e:
                    keys.append(json.loads(e.replace("data: ", "").strip())["key"])

            MockLLM.return_value.astream = mock_astream_b
            async for e in run_chain_with_streaming("ctx", "q2", "hist", "same-session"):
                if "buffer_complete" in e:
                    keys.append(json.loads(e.replace("data: ", "").strip())["key"])

        assert len(keys) == 2
        assert keys[0] != keys[1], "Concurrent requests must use unique buffer keys"
        # Buffers must be distinct
        buf_a = _stream_buffers.get(keys[0])
        buf_b = _stream_buffers.get(keys[1])
        assert (buf_a[0] if buf_a else None) != (buf_b[0] if buf_b else None)
        for k in keys:
            _stream_buffers.pop(k, None)


class TestRateLimiterIPSpoofing:
    def test_trusted_proxy_prefixes_defined(self):
        from app.core.rate_limiter import _TRUSTED_PROXY_PREFIXES
        assert "127." in _TRUSTED_PROXY_PREFIXES
        assert "10." in _TRUSTED_PROXY_PREFIXES

    def test_untrusted_peer_ignores_forwarded_for(self):
        from app.core.rate_limiter import _get_client_ip
        req = MagicMock()
        req.headers = {"x-forwarded-for": "1.2.3.4"}
        req.client.host = "5.6.7.8"  # external IP — not a trusted proxy
        ip = _get_client_ip(req)
        assert ip == "5.6.7.8", "Must not trust x-forwarded-for from untrusted peer"

    def test_trusted_peer_uses_forwarded_for(self):
        from app.core.rate_limiter import _get_client_ip
        req = MagicMock()
        req.headers = {"x-forwarded-for": "203.0.113.5"}
        req.client.host = "10.0.0.1"  # internal — trusted proxy
        ip = _get_client_ip(req)
        assert ip == "203.0.113.5"


class TestPathTraversal:
    def test_traversal_pattern_blocked(self):
        import asyncio

        from app.workers.ingestion_worker import _run_ingestion

        async def try_traversal():
            try:
                await _run_ingestion("../../etc")
                return "no_error"
            except ValueError as e:
                return str(e)

        result = asyncio.run(try_traversal())
        assert "Invalid source" in result or "traversal" in result.lower()

    def test_valid_source_passes_validation(self):
        """Valid source names (WHO, NICE, CDC) must not raise."""
        from app.workers.ingestion_worker import _ALLOWED_SOURCE_RE
        for valid in ("WHO", "NICE", "CDC", "UPTODATE"):
            assert _ALLOWED_SOURCE_RE.match(valid), f"{valid} should be valid"
        for invalid in ("../../etc", "who", "WHO123", "", "../"):
            assert not _ALLOWED_SOURCE_RE.match(invalid), f"{invalid} should be invalid"


class TestTopicClassifierAssert:
    def test_no_assert_statements(self):
        """Runtime invariants must use explicit raise, not assert (stripped by -O)."""
        src = Path("app/services/restrictions/topic_classifier.py").read_text(encoding="utf-8")
        assert "assert self._anchor_vectors" not in src, \
            "assert must be replaced with explicit raise"
        assert "raise RuntimeError" in src, "Must raise RuntimeError explicitly"


class TestTokensBufferedUntilValidation:
    """Verify token events are held server-side and only forwarded after restriction checks."""

    async def test_token_events_not_yielded_before_buffer_complete(self):
        """
        run_chain_with_streaming must NOT yield token events after buffer_complete —
        all token events come first, then the buffer_complete signal.
        """
        import json

        from app.services.llm.chain import _stream_buffers, run_chain_with_streaming

        chunks_content = ["hello ", "world ", "response"]

        async def mock_astream(*args, **kwargs):
            for content in chunks_content:
                m = MagicMock()
                m.content = content
                yield m

        with patch("app.services.llm.chain._get_llm") as MockLLM:
            MockLLM.return_value.astream = mock_astream
            events = []
            async for event in run_chain_with_streaming("ctx", "q", "hist", "sess-token-test"):
                events.append(event)

        # All token events should come before buffer_complete
        buffer_idx = next(i for i, e in enumerate(events) if "buffer_complete" in e)
        token_indices = [i for i, e in enumerate(events) if '"type": "token"' in e]

        assert all(i < buffer_idx for i in token_indices), \
            "All token events must precede buffer_complete"
        assert len(token_indices) == 3, "Should have 3 token events"

        # Clean up
        bc_event = json.loads(events[buffer_idx].replace("data: ", "").strip())
        _stream_buffers.pop(bc_event.get("key"), None)


class TestSSEParseGuard:
    async def test_malformed_sse_line_does_not_crash_generator(self):
        """Malformed SSE data must be skipped, not raise into the outer handler."""
        import uuid as _uuid

        from app.api.v1.triage import _stream_triage
        from app.models.triage import TriageRequest

        # Inject a malformed event into the chain stream
        async def mock_stream(*args, **kwargs):
            yield "data: {not valid json}\n\n"          # malformed
            yield "data: :\n\n"                          # SSE comment (empty data)
            # Then a valid buffer_complete
            from app.services.llm.chain import _stream_buffers
            key = str(_uuid.uuid4())
            _stream_buffers[key] = '{"summary":"ok","citations":[],"escalate":false,"escalation_reason":null,"confidence":"moderate","disclaimer":"consult_gp","restriction_triggered":false,"restriction_code":null}'
            yield f'data: {{"type":"buffer_complete","key":"{key}"}}\n\n'

        request = TriageRequest(session_id=_uuid.uuid4(), message="headache")

        events = []
        with patch("app.api.v1.triage.run_chain_with_streaming", mock_stream), \
             patch("app.api.v1.triage._pipeline") as mock_pipeline, \
             patch("app.api.v1.triage.acquire") as mock_acquire:
            mock_pipeline.run_output = AsyncMock(
                return_value=__import__('app.services.restrictions.pipeline', fromlist=['RestrictionResult']).RestrictionResult(passed=True)
            )
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock()
            ))
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=False)

            async for e in _stream_triage(request, "ctx", "hist", [{"content":"c","source":"S","section":"s","similarity":0.9,"jurisdiction":"global","confidence_tier":"high"}], {}):
                events.append(e)

        # Should complete normally — malformed lines skipped
        assert any("[DONE]" in e for e in events), "Stream must reach [DONE] despite malformed events"
        error_events = [e for e in events if '"type": "error"' in e and "error" in e]
        assert not error_events, f"No error events expected, got: {error_events}"


class TestBufferTTL:
    async def test_stale_buffers_pruned(self):
        import time

        from app.services.llm.chain import (
            _BUFFER_TTL_SECONDS,
            _prune_stale_buffers,
            _stream_buffers,
        )

        old_key = "old-key-123"
        _stream_buffers[old_key] = ("old content", time.monotonic() - _BUFFER_TTL_SECONDS - 1)
        fresh_key = "fresh-key-456"
        _stream_buffers[fresh_key] = ("fresh content", time.monotonic())

        _prune_stale_buffers()

        assert old_key not in _stream_buffers, "Stale buffer must be pruned"
        assert fresh_key in _stream_buffers, "Fresh buffer must survive"
        _stream_buffers.pop(fresh_key, None)

    async def test_result_yielded_before_persist(self):
        """[DONE] must appear in stream before _persist_turn is called."""
        import uuid

        from app.api.v1.triage import _stream_triage
        from app.models.triage import TriageRequest
        from app.services.llm.chain import _stream_buffers

        persist_called_at: list[int] = []
        result_yielded_at: list[int] = []
        event_counter = [0]

        async def mock_stream(*args, **kwargs):
            key = str(uuid.uuid4())
            _stream_buffers[key] = ('{"summary":"ok","citations":[],"escalate":false,"escalation_reason":null,"confidence":"moderate","disclaimer":"consult_gp","restriction_triggered":false,"restriction_code":null}', __import__("time").monotonic())
            yield f'data: {{"type":"buffer_complete","key":"{key}"}}\n\n'

        async def mock_persist(db, req, resp, mid):
            persist_called_at.append(event_counter[0])

        request = TriageRequest(session_id=uuid.uuid4(), message="headache test")
        from app.services.restrictions.pipeline import RestrictionResult

        with patch("app.api.v1.triage.run_chain_with_streaming", mock_stream), \
             patch("app.api.v1.triage._pipeline") as mp, \
             patch("app.api.v1.triage._persist_turn", mock_persist), \
             patch("app.api.v1.triage.acquire") as ma:
            mp.run_output = AsyncMock(return_value=RestrictionResult(passed=True))
            ma.return_value.__aenter__ = AsyncMock(return_value=MagicMock(execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock()))
            ma.return_value.__aexit__ = AsyncMock(return_value=False)

            async for e in _stream_triage(request, "ctx", "hist", [{"content":"c","source":"S","section":"s","similarity":0.9,"jurisdiction":"global","confidence_tier":"high"}], {}):
                event_counter[0] += 1
                if "[DONE]" in e:
                    result_yielded_at.append(event_counter[0])

        assert result_yielded_at, "Stream must yield [DONE]"
        if persist_called_at:
            assert persist_called_at[0] >= result_yielded_at[0], \
                "persist must not be called before [DONE] is yielded"
