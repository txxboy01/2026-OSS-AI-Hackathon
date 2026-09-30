import asyncio
import json
from email.message import Message

from pydantic import ValidationError
from starlette.requests import ClientDisconnect, Request

from .constants import MAX_REQUEST_BYTES
from .errors import SAFE_FIELDS, APIError


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _reject_constant(_value):
    raise ValueError("non-finite JSON number")


def strict_json_loads(text):
    # Bound parser nesting independently of the interpreter recursion limit.
    depth, in_string, escaped = 0, False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > 32:
                raise ValueError("JSON nesting limit")
        elif char in "]}":
            depth -= 1
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


async def read_json_model(request: Request, model):
    raw_type = request.headers.get("content-type", "")
    content = Message()
    content["content-type"] = raw_type
    params = content.get_params() or []
    if (
        content.get_content_type().lower() != "application/json"
        or len(request.headers.getlist("content-type")) != 1
        or any(k.lower() != "charset" or str(v).lower() != "utf-8" for k, v in params[1:])
        or len(params) > 2
        or request.headers.get("content-encoding", "identity").lower() != "identity"
    ):
        raise APIError("UNSUPPORTED_MEDIA_TYPE")
    length = request.headers.get("content-length")
    if length is not None:
        if not length.isascii() or not length.isdigit():
            raise APIError("INVALID_JSON")
        if int(length) > MAX_REQUEST_BYTES:
            raise APIError("PAYLOAD_TOO_LARGE")
    chunks = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(chunks) + len(chunk) > MAX_REQUEST_BYTES:
                    raise APIError("PAYLOAD_TOO_LARGE")
                chunks.extend(chunk)
        request.state.rpm_body_received_at = asyncio.get_running_loop().time()
        data = strict_json_loads(chunks.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError, TimeoutError):
        raise APIError("INVALID_JSON") from None
    except ClientDisconnect:
        raise asyncio.CancelledError() from None
    finally:
        chunks.clear()
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_context=False, include_url=False)
        # Pydantic rejects lone surrogates before our source policy validator.
        # Preserve the contract's 400 code and consent/length precedence.
        if (
            all(e["type"] == "string_unicode" and e["loc"] == ("messageText",) for e in errors)
            and 1 <= len(data["messageText"]) <= 5000
        ):
            if data["consentToExternalAi"] is False:
                raise APIError("CONSENT_REQUIRED", fields=["consentToExternalAi"]) from None
            raise APIError("INPUT_POLICY_VIOLATION", fields=["messageText"]) from None
        fields = {e["loc"][0] for e in errors if e["loc"] and e["loc"][0] in SAFE_FIELDS}
        raise APIError("INVALID_REQUEST", fields=fields) from None


def validate_message_policy(message):
    if not message.strip() or any(
        (ord(c) < 32 and c not in "\t\n\r") or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in message
    ):
        raise APIError("INPUT_POLICY_VIOLATION", fields=["messageText"])
