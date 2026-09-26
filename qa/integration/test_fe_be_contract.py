"""FE가 보내는 요청을 BE가 받아주고, BE 응답을 FE가 읽을 수 있는지 검증한다."""

import pytest
from app.constants import USER_ACTION_ORDER
from conftest import FE_ORIGINS, ExtractionFailure, FakeExtractor, fe_post

# FE 샘플 "로그인 유도" 본문에 실제로 들어 있는 문장
LOGIN_QUOTE = "아래 링크에서 로그인해 주세요."


def fe_analyze_body(text):
    # page.tsx runAnalysis(): messageText는 trim 후 전송, 동의는 true 고정
    return {"messageText": text.strip(), "consentToExternalAi": True}


# ---------------------------------------------------------------- 요청 계약


def test_fe_calls_only_endpoints_backend_serves(fe, make_client):
    paths = {route.path for route in make_client().app.routes}
    assert set(fe.endpoints) <= paths, f"BE에 없는 경로 호출: {set(fe.endpoints) - paths}"


def test_fe_request_fields_match_backend_schema(fe):
    from app.schemas import AnalyzeRequest, GuidanceRequest

    assert set(fe.request_keys("/analyze")) == set(AnalyzeRequest.model_fields)
    assert set(fe.request_keys("/guidance")) == set(GuidanceRequest.model_fields)


def test_fe_user_actions_are_accepted_by_backend(fe):
    assert set(fe.user_action_type) <= set(USER_ACTION_ORDER)
    assert set(fe.ui_actions) <= set(USER_ACTION_ORDER)


# ---------------------------------------------------------------- /analyze


@pytest.mark.parametrize("key", ["suncheon", "login", "app"])
def test_fe_sample_messages_pass_backend_input_policy(fe, make_client, key):
    """시연용 샘플이 개인정보 차단(400)에 걸리면 데모가 바로 실패한다."""
    fake = FakeExtractor()
    res = fe_post(make_client(fake), "/analyze", fe_analyze_body(fe.samples[key]))
    assert res.status_code == 200, res.json()
    assert fake.messages == [fe.samples[key].strip()]


def test_verified_response_has_every_field_fe_reads(fe, make_client):
    fake = FakeExtractor(evidence=[{"type": "ACT_LOGIN", "quote": LOGIN_QUOTE}])
    res = fe_post(make_client(fake), "/analyze", fe_analyze_body(fe.samples["login"]))
    body = res.json()

    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    assert body["status"] == "VERIFIED"
    assert set(fe.analyze_keys) <= set(body)
    for item in body["evidence"]:
        assert set(fe.evidence_keys) <= set(item)
        assert all(isinstance(item[k], str) for k in fe.evidence_keys)
    assert body["evidence"][0]["quote"] == LOGIN_QUOTE


@pytest.mark.parametrize(
    "extractor, status",
    [
        (FakeExtractor(evidence=[]), "NO_ACTION_FOUND"),
        (FakeExtractor(error=ExtractionFailure("AI_UNAVAILABLE")), "FALLBACK"),
        (FakeExtractor(evidence=[{"type": "ACT_LOGIN", "quote": "원문에 없는 문장"}]), "FALLBACK"),
    ],
    ids=["no-action", "ai-down", "fake-quote"],
)
def test_non_verified_statuses_are_known_to_fe(fe, make_client, extractor, status):
    res = fe_post(make_client(extractor), "/analyze", fe_analyze_body(fe.samples["login"]))
    body = res.json()
    assert res.status_code == 200
    assert body["status"] == status and body["status"] in fe.analyze_statuses
    assert body["evidence"] == []  # FE는 VERIFIED가 아니면 근거 카드를 그리지 않음
    assert body["notice"] and body["limitation"]


def test_ai_timeout_returns_fallback_not_error(fe, make_client):
    client = make_client(FakeExtractor(delay=1), ai_timeout_seconds=0.05)
    res = fe_post(client, "/analyze", fe_analyze_body(fe.samples["login"]))
    assert res.status_code == 200
    assert res.json()["status"] == "FALLBACK"


# ---------------------------------------------------------------- /guidance


def test_every_fe_action_button_gets_guidance(fe, make_client):
    client = make_client()
    for action in fe.ui_actions:
        res = fe_post(client, "/guidance", {"actions": [action]})
        body = res.json()
        assert res.status_code == 200, (action, body)
        assert set(fe.guidance_keys) <= set(body)
        assert body["urgency"] in ("routine", "prompt", "urgent")
        assert all({"code", "title", "body"} <= set(step) for step in body["steps"])


# ---------------------------------------------------------------- 오류 응답
# FE는 content-type이 JSON이 아니면 "서버 연결 상태를 확인해 주세요."를 띄우고,
# JSON이면 error.message를 사용자에게 그대로 보여준다.


def assert_fe_readable_error(res, status):
    assert res.status_code == status
    assert "application/json" in res.headers["content-type"]
    assert isinstance(res.json()["error"]["message"], str) and res.json()["error"]["message"]
    # CORS 헤더가 없으면 브라우저가 응답 본문을 막아 FE가 message를 못 읽는다
    assert res.headers.get("access-control-allow-origin") == FE_ORIGINS[0]


def test_sensitive_data_error_is_readable_by_fe(make_client):
    res = fe_post(make_client(), "/analyze", fe_analyze_body("010-1234-5678 로 연락 주세요"))
    assert_fe_readable_error(res, 400)
    assert "PHONE" in res.json()["error"]["detectedTypes"]


def test_too_long_message_error_is_readable_by_fe(make_client):
    # FE textarea에는 길이 제한이 없어서 5,000자를 넘는 입력이 그대로 전송된다
    res = fe_post(make_client(), "/analyze", fe_analyze_body("가" * 5001))
    assert_fe_readable_error(res, 422)


def test_rate_limit_error_is_readable_by_fe(fe, make_client):
    client = make_client(analyze_per_ip_per_minute=1)
    assert fe_post(client, "/analyze", fe_analyze_body(fe.samples["login"])).status_code == 200
    res = fe_post(client, "/analyze", fe_analyze_body(fe.samples["login"]))
    assert_fe_readable_error(res, 429)
    assert "retry-after" in res.headers.get("access-control-expose-headers", "").lower()


def test_unknown_path_error_is_readable_by_fe(make_client):
    assert_fe_readable_error(fe_post(make_client(), "/api/v1/analyze", {}), 404)


# ---------------------------------------------------------------- CORS


@pytest.mark.parametrize("origin", FE_ORIGINS)
@pytest.mark.parametrize("path", ["/analyze", "/guidance"])
def test_cors_preflight_allows_fe_origin(make_client, origin, path):
    res = make_client().options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == origin


def test_cors_rejects_unregistered_origin(make_client):
    res = fe_post(make_client(), "/guidance", {"actions": ["OPENED_LINK"]}, origin="https://evil.example")
    assert "access-control-allow-origin" not in res.headers
