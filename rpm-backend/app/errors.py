from starlette.responses import JSONResponse

from .constants import ERROR_MESSAGES, ERROR_STATUS, PII_ORDER
from .schemas import ErrorDetail, ErrorResponse

SAFE_FIELDS = ("messageText", "consentToExternalAi", "actions")


class APIError(Exception):
    """Carries public codes only. Never attach input, exceptions, or provider data."""

    def __init__(self, code, *, fields=(), detected_types=(), retry_after=None):
        if code not in ERROR_STATUS:
            raise ValueError("invalid public error code")
        super().__init__(code)
        self.code = code
        self.fields = [x for x in SAFE_FIELDS if x in fields]
        self.detected_types = [x for x in PII_ORDER if x in detected_types]
        self.retry_after = retry_after


class ExtractionFailure(Exception):
    def __init__(self, reason):
        from typing import get_args

        from .constants import FallbackReason

        if reason not in get_args(FallbackReason):
            raise ValueError("invalid fallback reason")
        super().__init__(reason)
        self.reason = reason


def error_response(scope, error, headers=None):
    scope.setdefault("state", {})["rpm_error_code"] = error.code
    body = ErrorResponse(
        requestId=scope["state"]["rpm_request_id"],
        error=ErrorDetail(
            code=error.code,
            message=ERROR_MESSAGES[error.code],
            fields=error.fields,
            detectedTypes=error.detected_types,
        ),
    )
    response_headers = dict(headers or {})
    if error.retry_after is not None:
        response_headers["Retry-After"] = str(max(1, error.retry_after))
    return JSONResponse(
        body.model_dump(mode="json"), status_code=ERROR_STATUS[error.code], headers=response_headers
    )
