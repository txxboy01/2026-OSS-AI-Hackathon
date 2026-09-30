import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from .config import Settings
from .errors import APIError, ExtractionFailure, error_response
from .extractor import GeminiExtractor
from .fallback import build_fallback
from .guidance import get_guidance
from .json_io import read_json_model, validate_message_policy
from .limits import RequestLimits
from .middleware import ErrorBoundary, RequestMetadata
from .redactor import detect_sensitive
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    GuidanceRequest,
    GuidanceResponse,
    HealthResponse,
    NoActionResponse,
    VerifiedResponse,
)
from .validator import validate


async def _wait_for_disconnect(request):
    while True:
        event = await request.receive()
        if event["type"] == "http.disconnect":
            return


async def _analyze_with_disconnect(request, operation):
    work = asyncio.create_task(operation())
    disconnect = asyncio.create_task(_wait_for_disconnect(request))
    try:
        completed, _ = await asyncio.wait((work, disconnect), return_when=asyncio.FIRST_COMPLETED)
        if disconnect in completed:
            raise asyncio.CancelledError()
        return await work
    finally:
        for task in (work, disconnect):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, disconnect, return_exceptions=True)


def create_app(settings=None, extractor=None):
    settings = settings or Settings()
    if extractor is not None and settings.app_env != "test":
        raise ValueError("injected extractors are restricted to test environment")
    if settings.app_env == "test" and extractor is None:
        raise ValueError("test environment requires an explicit test extractor")

    @asynccontextmanager
    async def lifespan(app):
        instance = extractor if extractor is not None else GeminiExtractor(settings)
        app.state.extractor = instance
        try:
            yield
        finally:
            await instance.aclose()

    app = FastAPI(
        title="RPM Backend API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
        redirect_slashes=False,
    )
    app.state.settings = settings
    app.state.limits = RequestLimits(settings)
    contract = yaml.safe_load(
        (Path(__file__).resolve().parent.parent / "docs/openapi-v1.yaml").read_text(encoding="utf-8")
    )
    app.openapi = lambda: contract

    @app.exception_handler(APIError)
    async def api_error(request, exc):
        return error_response(request.scope, exc)

    @app.exception_handler(RequestValidationError)
    async def framework_validation_error(request, _exc):
        return error_response(request.scope, APIError("INVALID_REQUEST"))

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "INTERNAL_ERROR")
        headers = (
            {"Allow": exc.headers["Allow"]}
            if exc.status_code == 405 and exc.headers and "Allow" in exc.headers
            else {}
        )
        return error_response(request.scope, APIError(code), headers=headers)

    @app.get("/health", response_model=HealthResponse)
    async def health():
        return HealthResponse()

    @app.post("/analyze", response_model=AnalyzeResponse)
    async def analyze(request: Request):
        payload = await read_json_model(request, AnalyzeRequest)
        if not payload.consentToExternalAi:
            raise APIError("CONSENT_REQUIRED", fields=["consentToExternalAi"])
        message = payload.messageText
        validate_message_policy(message)
        found = detect_sensitive(message)
        if found:
            raise APIError("SENSITIVE_DATA_DETECTED", fields=["messageText"], detected_types=found)
        ip = request.client.host if request.client else "unknown"
        request_id = request.state.rpm_request_id

        async def operation():
            deadline = request.state.rpm_body_received_at + settings.analyze_deadline_seconds
            async with asyncio.timeout_at(deadline):
                async with asyncio.timeout(settings.ai_timeout_seconds):
                    envelope = await app.state.extractor.extract(message)
                evidence = validate(message, envelope)
                return (
                    VerifiedResponse(requestId=request_id, evidence=evidence)
                    if evidence
                    else NoActionResponse(requestId=request_id)
                )

        async with app.state.limits.analysis(ip):
            try:
                result = await _analyze_with_disconnect(request, operation)
            except TimeoutError:
                result = build_fallback(request_id, "AI_TIMEOUT")
            except ExtractionFailure as exc:
                result = build_fallback(request_id, exc.reason)
        request.state.rpm_analysis_status = result.status
        if result.reasonCode:
            request.state.rpm_reason_code = result.reasonCode
        return result

    @app.post("/guidance", response_model=GuidanceResponse)
    async def guidance(request: Request):
        payload = await read_json_model(request, GuidanceRequest)
        app.state.limits.guidance(request.client.host if request.client else "unknown")
        return get_guidance(payload.actions, request.state.rpm_request_id)

    # Registration order is reversed by Starlette when building the ASGI stack.
    app.add_middleware(ErrorBoundary)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestMetadata)
    return app
