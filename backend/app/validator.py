"""Validate Gemini evidence against the exact message sent for analysis."""

import json
from typing import Any


TYPE_LABELS = {
    "ACT_LOGIN": "로그인 요구",
    "ACT_PAYMENT": "결제·송금 요구",
    "ACT_APP": "앱 설치 요구",
    "ACT_LINK": "링크 접속 요구",
    "ACT_PERSONAL": "개인정보 요구",
    "PRESSURE": "긴급성 강조",
}


class EvidenceValidationError(ValueError):
    """The AI result cannot be safely displayed."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceValidationError("Duplicate AI result field")
        result[key] = value
    return result


def validate_evidence(message: str, raw_response: str | dict[str, Any]) -> list[dict[str, str]]:
    """Return server-labelled evidence, or reject the entire AI result.

    The AI contract is exactly {"evidence": [{"type": ..., "quote": ...}]}.
    Empty evidence is valid when no requested action is found. Quotes are compared
    to the unmodified analysis message; even whitespace differences are rejected.
    """
    if not isinstance(message, str):
        raise EvidenceValidationError("Invalid analysis message")

    try:
        payload = json.loads(raw_response, object_pairs_hook=_reject_duplicate_keys) if isinstance(raw_response, str) else raw_response
    except (json.JSONDecodeError, TypeError) as exc:
        raise EvidenceValidationError("Malformed AI JSON") from exc

    if not isinstance(payload, dict) or set(payload) != {"evidence"}:
        raise EvidenceValidationError("Unexpected AI result fields")

    items = payload["evidence"]
    if not isinstance(items, list):
        raise EvidenceValidationError("Evidence must be an array")

    verified: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"type", "quote"}:
            raise EvidenceValidationError("Unexpected evidence fields")
        evidence_type = item["type"]
        quote = item["quote"]
        if not isinstance(evidence_type, str) or evidence_type not in TYPE_LABELS:
            raise EvidenceValidationError("Unknown evidence type")
        if not isinstance(quote, str) or not quote.strip() or quote not in message:
            raise EvidenceValidationError("Quote is empty or absent from the message")
        verified.append({"type": evidence_type, "label": TYPE_LABELS[evidence_type], "quote": quote})

    return verified
