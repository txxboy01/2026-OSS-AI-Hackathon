import json
import logging
import time
import uuid
from datetime import UTC, datetime

from .errors import APIError, error_response

LOGGER = logging.getLogger("rpm.events")
ROUTES = {"/health", "/analyze", "/guidance", "/docs", "/docs/oauth2-redirect", "/openapi.json"}


class ErrorBoundary:
    """Inside CORS: even an unexpected 500 gets the approved origin headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def observe(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, observe)
        except Exception:
            # No exception object, traceback, locals, path or request data is logged.
            if started:
                raise
            response = error_response(scope, APIError("INTERNAL_ERROR"))
            await response(scope, receive, send)


class RequestMetadata:
    """Outermost app middleware: bounded safe metadata only, including OPTIONS."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        state = scope.setdefault("state", {})
        state["rpm_request_id"] = str(uuid.uuid4())
        started = time.monotonic()
        status = 499

        async def add_headers(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in {b"cache-control", b"x-request-id"}
                ]
                headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-request-id", state["rpm_request_id"].encode("ascii")),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, add_headers)
        finally:
            route = scope.get("path")
            event = {
                "timestamp": datetime.now(UTC).isoformat(),
                "requestId": state["rpm_request_id"],
                "route": route if route in ROUTES else "unmatched",
                "httpStatus": status,
                "latencyMs": round((time.monotonic() - started) * 1000, 2),
            }
            for key, output in [
                ("rpm_error_code", "errorCode"),
                ("rpm_analysis_status", "status"),
                ("rpm_reason_code", "reasonCode"),
            ]:
                if key in state:
                    event[output] = state[key]
            LOGGER.info(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
