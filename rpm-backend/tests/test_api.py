import json
import logging
import uuid

import pytest
from conftest import FakeExtractor, envelope
from fastapi.testclient import TestClient

from app.errors import ExtractionFailure
from app.extractor import ExtractionEnvelope

BODY = {"messageText": "🔐 아래 링크에서 로그인하세요.", "consentToExternalAi": True}


def check_error(response, status, code):
    assert response.status_code == status, response.text
    data = response.json()
    assert set(data) == {"requestId", "apiVersion", "error"}
    assert data["error"]["code"] == code
    assert response.headers["x-request-id"] == data["requestId"]
    assert response.headers["cache-control"] == "no-store"
    uuid.UUID(data["requestId"])
    return data["error"]


def test_health_and_no_action(client):
    c, fake = client
    assert c.get("/health").json() == {"status": "ok", "service": "rpm-backend", "apiVersion": "1.0"}
    assert fake.calls == 0
    response = c.post("/analyze", json=BODY)
    assert response.status_code == 200
    assert response.json()["status"] == "NO_ACTION_FOUND"
    assert response.json()["evidence"] == []
    assert fake.calls == 1
    assert fake.messages == [BODY["messageText"]]


def test_verified_contract(factory):
    quote = "아래 링크에서 로그인하세요."
    app, fake = factory(FakeExtractor(envelope([{"type": "ACT_LOGIN", "quote": quote}])))
    with TestClient(app) as c:
        response = c.post("/analyze", json=BODY)
        data = response.json()
        assert data["status"] == "VERIFIED"
        assert data["evidence"][0]["spans"] == [{"start": 3, "end": 18}]
        assert data["notice"] and data["limitation"]
        assert data["requestId"] == response.headers["x-request-id"]
        assert response.headers["cache-control"] == "no-store"
    assert fake.closed


@pytest.mark.parametrize(
    "patch,status,code",
    [
        ({"consentToExternalAi": False}, 400, "CONSENT_REQUIRED"),
        ({"consentToExternalAi": "true"}, 422, "INVALID_REQUEST"),
        ({"consentToExternalAi": 1}, 422, "INVALID_REQUEST"),
        ({"messageText": ""}, 422, "INVALID_REQUEST"),
        ({"messageText": "가" * 5001}, 422, "INVALID_REQUEST"),
        ({"messageText": 1}, 422, "INVALID_REQUEST"),
        ({"messageText": None}, 422, "INVALID_REQUEST"),
        ({"messageText": "  \n\t"}, 400, "INPUT_POLICY_VIOLATION"),
        ({"messageText": "\x00로그인"}, 400, "INPUT_POLICY_VIOLATION"),
        ({"messageText": "로그인\x7f"}, 400, "INPUT_POLICY_VIOLATION"),
        ({"forceError": True}, 422, "INVALID_REQUEST"),
    ],
)
def test_request_validation(client, patch, status, code):
    c, fake = client
    check_error(c.post("/analyze", json={**BODY, **patch}), status, code)
    assert fake.calls == 0


@pytest.mark.parametrize("value", [{}, {"messageText": "hello"}, [], None, True, "string"])
def test_missing_or_wrong_root(client, value):
    c, fake = client
    check_error(
        c.post("/analyze", content=json.dumps(value), headers={"Content-Type": "application/json"}),
        422,
        "INVALID_REQUEST",
    )
    assert fake.calls == 0


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"\xff",
        b'{"messageText":"x","messageText":"y","consentToExternalAi":true}',
        b'{"messageText":NaN}',
        b"[" * 1100 + b"]" * 1100,
    ],
)
def test_bad_json(client, raw):
    c, fake = client
    check_error(
        c.post("/analyze", content=raw, headers={"Content-Type": "application/json"}), 400, "INVALID_JSON"
    )
    assert fake.calls == 0


def test_surrogate_is_policy_error(client):
    c, _ = client
    raw = json.dumps({"messageText": "\ud800", "consentToExternalAi": True})
    check_error(
        c.post("/analyze", content=raw, headers={"Content-Type": "application/json"}),
        400,
        "INPUT_POLICY_VIOLATION",
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "text/plain"},
        {"Content-Type": "application/json; charset=latin1"},
        {"Content-Type": "application/json", "Content-Encoding": "gzip"},
        {"Content-Type": "application/json; weird=x"},
        {},
    ],
)
def test_media_type(client, headers):
    c, _ = client
    check_error(c.post("/analyze", content=b"{}", headers=headers), 415, "UNSUPPORTED_MEDIA_TYPE")


def test_json_utf8_charset(client):
    c, _ = client
    assert (
        c.post(
            "/analyze", content=json.dumps(BODY), headers={"Content-Type": "application/json; charset=UTF-8"}
        ).status_code
        == 200
    )


def test_body_size(client):
    c, fake = client
    check_error(
        c.post("/analyze", content=b" " * 32769, headers={"Content-Type": "application/json"}),
        413,
        "PAYLOAD_TOO_LARGE",
    )
    assert fake.calls == 0


def test_sensitive_data_no_external_call(client):
    c, fake = client
    error = check_error(
        c.post("/analyze", json={**BODY, "messageText": "전화 010-0000-0000"}), 400, "SENSITIVE_DATA_DETECTED"
    )
    assert error["detectedTypes"] == ["PHONE", "ACCOUNT"]
    assert "010" not in json.dumps(error)
    assert fake.calls == 0


@pytest.mark.parametrize(
    "result,reason",
    [
        (envelope([{"type": "ACT_LOGIN", "quote": "원문에 없는 인용"}]), "EVIDENCE_INVALID"),
        (ExtractionEnvelope("invalid"), "AI_OUTPUT_INVALID"),
        (ExtractionEnvelope("blocked"), "AI_BLOCKED"),
        (ExtractionEnvelope("completed", '{"evidence":[],"isPhishing":true}'), "AI_OUTPUT_INVALID"),
    ],
)
def test_fallback(factory, result, reason):
    app, fake = factory(FakeExtractor(result))
    with TestClient(app) as c:
        response = c.post("/analyze", json=BODY)
        data = response.json()
        assert response.status_code == 200
        assert data["mode"] == "fallback" and data["status"] == "FALLBACK"
        assert data["reasonCode"] == reason and data["evidence"] == []
        assert fake.calls == 1
        assert "원문에 없는 인용" not in response.text
        assert app.state.limits.active == 0


@pytest.mark.parametrize("reason", ["AI_UNAVAILABLE", "AI_TIMEOUT"])
def test_provider_failure(factory, reason):
    app, fake = factory(FakeExtractor(error=ExtractionFailure(reason)))
    with TestClient(app) as c:
        response = c.post("/analyze", json=BODY)
        assert response.status_code == 200 and response.json()["reasonCode"] == reason
        assert fake.calls == 1 and app.state.limits.active == 0


def test_timeout_releases_slot(factory):
    app, fake = factory(FakeExtractor(delay=0.2), ai_timeout_seconds=0.01, analyze_deadline_seconds=0.03)
    with TestClient(app) as c:
        assert c.post("/analyze", json=BODY).json()["reasonCode"] == "AI_TIMEOUT"
        assert fake.cancelled and fake.calls == 1 and app.state.limits.active == 0


def test_unexpected_exception_safe_with_cors(factory, caplog):
    marker = "UNIQUE_PRIVATE_ERROR_MARKER"
    app, _fake = factory(FakeExtractor(error=RuntimeError(marker)))
    with (
        TestClient(app, raise_server_exceptions=False) as c,
        caplog.at_level(logging.INFO, logger="rpm.events"),
    ):
        response = c.post("/analyze", json=BODY, headers={"Origin": "http://localhost:3000"})
        check_error(response, 500, "INTERNAL_ERROR")
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert marker not in response.text + caplog.text
        assert app.state.limits.active == 0


def test_errors_do_not_reflect_dynamic_input(client, caplog):
    c, fake = client
    marker = "UNIQUE_PRIVATE_INPUT_MARKER"
    with caplog.at_level(logging.INFO, logger="rpm.events"):
        r = c.post("/analyze?raw=" + marker, json={**BODY, marker: marker}, headers={"X-Request-ID": marker})
        error = check_error(r, 422, "INVALID_REQUEST")
        assert error["fields"] == []
        assert marker not in r.text + caplog.text
        r = c.get("/not-found/" + marker)
        check_error(r, 404, "NOT_FOUND")
        assert marker not in r.text + caplog.text
    assert fake.calls == 0


def test_cors_and_methods(client):
    c, _ = client
    ok = c.options(
        "/analyze",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"
    assert "access-control-allow-credentials" not in ok.headers
    bad = c.post("/guidance", json={"actions": ["UNKNOWN"]}, headers={"Origin": "https://untrusted.invalid"})
    assert "access-control-allow-origin" not in bad.headers
    check_error(c.get("/analyze"), 405, "METHOD_NOT_ALLOWED")
    check_error(c.post("/analyze/"), 404, "NOT_FOUND")


def test_openapi_exposes_canonical_contract(client):
    c, _ = client
    spec = c.get("/openapi.json").json()
    assert set(spec["paths"]) == {"/health", "/analyze", "/guidance"}
    assert c.get("/docs").status_code == 200


def test_rate_limit_http(client):
    c, fake = client
    for _ in range(5):
        assert c.post("/analyze", json=BODY).status_code == 200
    response = c.post("/analyze", json=BODY)
    check_error(response, 429, "RATE_LIMITED")
    assert int(response.headers["retry-after"]) > 0 and fake.calls == 5
