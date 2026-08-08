import logging
import time
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    """
    Pure ASGI middleware — does NOT subclass BaseHTTPMiddleware.

    BaseHTTPMiddleware buffers the entire response body before returning,
    which breaks SSE streaming. This implementation wraps Send directly
    and injects the X-Request-ID header into the initial response message
    without touching the body stream at all.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = (
            headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())
        )

        # Attach to scope so route handlers can access it
        # Use setdefault pattern — never overwrite existing state set by earlier middleware
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        start = time.perf_counter()

        async def send_with_request_id(message) -> None:
            if message["type"] == "http.response.start":
                # Inject header without buffering body
                existing = list(message.get("headers", []))
                existing.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": existing}

                duration_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "request path=%s method=%s status=%d duration_ms=%.1f request_id=%s",
                    scope.get("path", ""),
                    scope.get("method", ""),
                    message.get("status", 0),
                    duration_ms,
                    request_id,
                )
            await send(message)

        await self.app(scope, receive, send_with_request_id)
