from pydantic import ValidationError

from .constants import ACTION_LABELS, ACTION_ORDER, MAX_AI_OUTPUT_BYTES, MAX_SPANS_PER_QUOTE
from .errors import ExtractionFailure
from .json_io import strict_json_loads
from .schemas import Evidence, RawExtraction, Span


def validate(message, envelope):
    if envelope.status == "blocked":
        raise ExtractionFailure("AI_BLOCKED")
    if envelope.status != "completed" or not isinstance(envelope.text, str):
        raise ExtractionFailure("AI_OUTPUT_INVALID")
    try:
        if len(envelope.text.encode("utf-8")) > MAX_AI_OUTPUT_BYTES:
            raise ValueError("oversized output")
        raw = RawExtraction.model_validate(strict_json_loads(envelope.text))
    except (ValueError, UnicodeError, RecursionError, ValidationError):
        raise ExtractionFailure("AI_OUTPUT_INVALID") from None

    # Prefix table preserves code points exactly, including CRLF and decomposed Hangul.
    utf16 = [0]
    for char in message:
        utf16.append(utf16[-1] + (2 if ord(char) > 0xFFFF else 1))
    candidates = {}
    for item in raw.evidence:
        spans = []
        cursor = 0
        while True:
            start = message.find(item.quote, cursor)
            if start == -1:
                break
            if len(spans) == MAX_SPANS_PER_QUOTE:
                raise ExtractionFailure("EVIDENCE_INVALID")
            spans.append(Span(start=utf16[start], end=utf16[start + len(item.quote)]))
            cursor = start + 1  # Overlapping occurrences are intentional.
        if not spans:
            raise ExtractionFailure("EVIDENCE_INVALID")
        candidates[(item.type, item.quote)] = spans
    ordered = sorted(
        candidates.items(),
        key=lambda entry: (
            entry[1][0].start,
            ACTION_ORDER.index(entry[0][0]),
            entry[0][1],
        ),
    )
    return [
        Evidence(id=f"e{i}", type=kind, label=ACTION_LABELS[kind], quote=quote, spans=spans)
        for i, ((kind, quote), spans) in enumerate(ordered, 1)
    ]
