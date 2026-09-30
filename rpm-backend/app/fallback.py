from .schemas import FallbackResponse


def build_fallback(request_id, reason_code):
    return FallbackResponse(requestId=request_id, reasonCode=reason_code)
