import json

import pytest
from conftest import envelope

from app.errors import ExtractionFailure
from app.extractor import ExtractionEnvelope
from app.validator import validate


def test_offsets_sort_and_dedup():
    message = "🔐 로그인하세요\r\n로그인하세요"
    result = validate(
        message,
        envelope(
            [
                {"type": "ACT_LOGIN", "quote": "로그인하세요"},
                {"type": "ACT_LOGIN", "quote": "로그인하세요"},
                {"type": "ACT_LINK", "quote": "로그인하세요"},
            ]
        ),
    )
    assert [x.id for x in result] == ["e1", "e2"]
    assert [x.type for x in result] == ["ACT_LOGIN", "ACT_LINK"]
    assert [(s.start, s.end) for s in result[0].spans] == [(3, 9), (11, 17)]
    for item in result:
        for span in item.spans:
            assert (
                message.encode("utf-16-le")[span.start * 2 : span.end * 2].decode("utf-16-le") == item.quote
            )


@pytest.mark.parametrize(
    "items, reason",
    [
        ([{"type": "ACT_LOGIN", "quote": "login"}], "EVIDENCE_INVALID"),
        ([{"type": "ACT_LOGIN", "quote": ""}], "AI_OUTPUT_INVALID"),
        ([{"type": "ACT_LOGIN", "quote": " \n"}], "AI_OUTPUT_INVALID"),
        ([{"type": "FAKE", "quote": "로그인하세요"}], "AI_OUTPUT_INVALID"),
        ([{"type": "ACT_LOGIN", "quote": 7}], "AI_OUTPUT_INVALID"),
        ([{"type": "ACT_LOGIN", "quote": None}], "AI_OUTPUT_INVALID"),
        ([{"type": "ACT_LOGIN", "quote": "로그인하세요", "riskScore": 99}], "AI_OUTPUT_INVALID"),
        (
            [{"type": "ACT_LOGIN", "quote": "로그인하세요"}, {"type": "ACT_APP", "quote": "앱 설치"}],
            "EVIDENCE_INVALID",
        ),
        ([{"type": "ACT_LOGIN", "quote": "로그인하세요"}] * 13, "AI_OUTPUT_INVALID"),
        ([{"type": "ACT_LOGIN", "quote": "\ud800"}], "AI_OUTPUT_INVALID"),
    ],
)
def test_invalid_items(items, reason):
    raw = ExtractionEnvelope("completed", json.dumps({"evidence": items}))
    with pytest.raises(ExtractionFailure, match=reason):
        validate("로그인하세요", raw)


@pytest.mark.parametrize(
    "text",
    [
        "",
        '```json\n{"evidence":[]}\n```',
        "null",
        "[]",
        '{"evidence":[],"evidence":[]}',
        '{"evidence":[],"diagnosis":"safe"}',
        '{"evidence":NaN}',
        '{"evidence":Infinity}',
        "x" * 32769,
        "[" * 1100 + "]" * 1100,
    ],
)
def test_invalid_json(text):
    with pytest.raises(ExtractionFailure, match="AI_OUTPUT_INVALID"):
        validate("원문", ExtractionEnvelope("completed", text))


@pytest.mark.parametrize("status,reason", [("blocked", "AI_BLOCKED"), ("invalid", "AI_OUTPUT_INVALID")])
def test_finish_states(status, reason):
    with pytest.raises(ExtractionFailure, match=reason):
        validate("원문", ExtractionEnvelope(status, '{"evidence":[]}'))


def test_empty_and_quote_length_edges():
    assert validate("공지", envelope([])) == []
    assert len(validate("가" * 500, envelope([{"type": "ACT_LINK", "quote": "가" * 500}]))) == 1
    with pytest.raises(ExtractionFailure, match="AI_OUTPUT_INVALID"):
        validate("가" * 501, envelope([{"type": "ACT_LINK", "quote": "가" * 501}]))
    assert len(validate("로그인하세요", envelope([{"type": "ACT_LOGIN", "quote": "로그인하세요"}] * 12))) == 1


def test_repeated_and_overlapping_occurrences():
    result = validate("a" * 21, envelope([{"type": "ACT_LINK", "quote": "aa"}]))
    assert len(result[0].spans) == 20
    with pytest.raises(ExtractionFailure, match="EVIDENCE_INVALID"):
        validate("a" * 22, envelope([{"type": "ACT_LINK", "quote": "aa"}]))


@pytest.mark.parametrize(
    "source,quote", [("가", "가"), ("A", "a"), ("a\r\nb", "a\nb"), ("로그인하세요.", "로그인 하세요.")]
)
def test_no_normalization(source, quote):
    with pytest.raises(ExtractionFailure, match="EVIDENCE_INVALID"):
        validate(source, envelope([{"type": "ACT_LOGIN", "quote": quote}]))


def test_quote_is_inert_evidence_not_sanitized_or_rewritten():
    quote = "<script>fake()</script> 안전한 앱을 설치하세요"
    result = validate(quote, envelope([{"type": "ACT_APP", "quote": quote}]))
    assert result[0].quote == quote  # Consumer must render as text, never innerHTML.
