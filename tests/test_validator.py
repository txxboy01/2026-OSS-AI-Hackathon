import json

import pytest

from backend.app.validator import EvidenceValidationError, validate_evidence


MESSAGE = "오늘 안에 계정을 확인하세요. 아래 링크에서 로그인하세요."


def test_valid_exact_quote_gets_server_owned_label():
    raw = json.dumps({"evidence": [{"type": "ACT_LOGIN", "quote": "아래 링크에서 로그인하세요"}]})
    assert validate_evidence(MESSAGE, raw) == [
        {"type": "ACT_LOGIN", "label": "로그인 요구", "quote": "아래 링크에서 로그인하세요"}
    ]


def test_no_action_can_return_empty_evidence():
    assert validate_evidence(MESSAGE, '{"evidence": []}') == []


@pytest.mark.parametrize(
    "raw",
    [
        '{"evidence": [{"type": "ACT_LOGIN", "quote": ""}]}',
        '{"evidence": [{"type": "ACT_LOGIN", "quote": "   "}]}',
        '{"evidence": [{"type": "ACT_LOGIN", "quote": "다른 링크에서 로그인하세요"}]}',
        '{"evidence": [{"type": "PHISHING", "quote": "아래 링크에서 로그인하세요"}]}',
        '{"evidence": [{"type": "ACT_LOGIN", "quote": "아래 링크에서 로그인하세요", "verdict": "피싱 확정"}]}',
        '{"evidence": [], "verdict": "피싱 확정"}',
        '{"evidence": [{"type": "ACT_LOGIN", "quote": "아래 링크에서 로그인하세요", "label": "안전한 링크"}]}',
        '{"evidence": [1]}',
        '{"evidence": "not an array"}',
        '{"evidence": [}',
        '{"evidence": [], "evidence": [{"type":"ACT_LOGIN","quote":"아래 링크에서 로그인하세요"}]}',
        '{"evidence": [{"type":"ACT_LOGIN","type":"ACT_APP","quote":"아래 링크에서 로그인하세요"}]}',
    ],
)
def test_invalid_ai_result_is_rejected(raw):
    with pytest.raises(EvidenceValidationError):
        validate_evidence(MESSAGE, raw)


def test_any_invalid_item_rejects_full_result():
    raw = {
        "evidence": [
            {"type": "ACT_LOGIN", "quote": "아래 링크에서 로그인하세요"},
            {"type": "ACT_APP", "quote": "앱을 설치하세요"},
        ]
    }
    with pytest.raises(EvidenceValidationError):
        validate_evidence(MESSAGE, raw)
