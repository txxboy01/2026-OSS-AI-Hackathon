import json

import pytest

from backend.app import extractor
from backend.app.extractor import MAX_MESSAGE_BYTES, MAX_RESPONSE_BYTES, analyze_message
from backend.app.fallback import FALLBACK_MESSAGE, LIMITATION


MESSAGE = "아래 링크에서 로그인하세요"


def response(text, finish_reason="STOP"):
    return json.dumps(
        {"candidates": [{"finishReason": finish_reason, "content": {"parts": [{"text": text}]}}]}
    ).encode()


def test_gemini_request_and_valid_result():
    calls = []

    def transport(body, api_key, model):
        calls.append((json.loads(body), api_key, model))
        return response('{"evidence":[{"type":"ACT_LOGIN","quote":"아래 링크에서 로그인하세요"}]}')

    result = analyze_message(MESSAGE, api_key="test-key", model="gemini-3.5-flash-lite", transport=transport)
    assert result == {
        "mode": "ai",
        "evidence": [{"type": "ACT_LOGIN", "label": "로그인 요구", "quote": MESSAGE}],
        "limitation": LIMITATION,
    }
    body, key, model = calls[0]
    assert key == "test-key"
    assert model == "gemini-3.5-flash-lite"
    assert body["contents"][0]["parts"][0]["text"] == MESSAGE
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseSchema"]["required"] == ["evidence"]
    assert body["generationConfig"]["responseSchema"]["additionalProperties"] is False
    assert body["generationConfig"]["responseSchema"]["properties"]["evidence"]["items"]["additionalProperties"] is False


def test_bad_quote_falls_back_without_ai_evidence():
    result = analyze_message(
        MESSAGE,
        api_key="test-key",
        transport=lambda *_: response('{"evidence":[{"type":"ACT_LOGIN","quote":"없는 문장"}]}'),
    )
    assert result == {"mode": "fallback", "evidence": [], "limitation": LIMITATION, "message": FALLBACK_MESSAGE}


def test_malformed_json_and_interrupted_generation_fall_back():
    for raw in [response("not json"), response('{"evidence":[]}', "MAX_TOKENS")]:
        result = analyze_message(MESSAGE, api_key="test-key", transport=lambda *_: raw)
        assert result["mode"] == "fallback"
        assert result["evidence"] == []


def test_transport_error_and_missing_key_fall_back(monkeypatch):
    def failing_transport(*_):
        raise RuntimeError("sensitive details must not escape")

    result = analyze_message(MESSAGE, api_key="test-key", transport=failing_transport)
    assert result["mode"] == "fallback"
    assert "sensitive details" not in str(result)

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = analyze_message(MESSAGE, transport=failing_transport)
    assert result["mode"] == "fallback"


def test_thought_part_is_ignored_and_signature_on_answer_is_accepted():
    raw = json.dumps(
        {
            "candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [
                    {"thought": True, "text": "unverified reasoning"},
                    {"text": '{"evidence":[{"type":"ACT_LOGIN","quote":"아래 링크에서 로그인하세요"}]}',
                     "thoughtSignature": "opaque-signature"},
                ]},
            }]
        }
    ).encode()
    result = analyze_message(MESSAGE, api_key="test-key", transport=lambda *_: raw)
    assert result["mode"] == "ai"
    assert result["evidence"][0]["quote"] == MESSAGE


@pytest.mark.parametrize(
    "parts",
    [
        [{"thought": True, "text": "only thoughts"}],
        [{"text": '{"evidence":[]}'}, {"text": '{"evidence":[]}'}],
        [{"functionCall": {"name": "unexpected"}}],
        [{"text": '{"evidence":[]}', "functionCall": {"name": "unexpected"}}],
        ["not an object"],
    ],
)
def test_ambiguous_parts_fail_closed(parts):
    raw = json.dumps({"candidates": [{"finishReason": "STOP", "content": {"parts": parts}}]}).encode()
    assert analyze_message(MESSAGE, api_key="test-key", transport=lambda *_: raw)["mode"] == "fallback"


@pytest.mark.parametrize("message", [None, 123, "", "   ", "x" * (MAX_MESSAGE_BYTES + 1), "\ud800"])
def test_invalid_or_oversized_input_never_reaches_transport(message):
    calls = []

    def transport(*args):
        calls.append(args)
        return response('{"evidence":[]}')

    assert analyze_message(message, api_key="test-key", transport=transport)["mode"] == "fallback"
    assert calls == []


@pytest.mark.parametrize("raw", ["not bytes", b"x" * (MAX_RESPONSE_BYTES + 1), b"[]", b"{}"])
def test_invalid_or_oversized_upstream_response_falls_back(raw):
    result = analyze_message(MESSAGE, api_key="test-key", transport=lambda *_: raw)
    assert result["mode"] == "fallback"
    assert result["evidence"] == []


def test_rest_request_keeps_api_key_out_of_url_and_limits_read(monkeypatch):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, size):
            calls.append(size)
            return response('{"evidence":[]}')

    def fake_urlopen(request, timeout):
        assert "test-key" not in request.full_url
        assert request.get_header("X-goog-api-key") == "test-key"
        assert timeout == extractor.REQUEST_TIMEOUT_SECONDS
        return FakeResponse()

    monkeypatch.setattr(extractor, "urlopen", fake_urlopen)
    result = analyze_message(MESSAGE, api_key="test-key")
    assert result["mode"] == "ai"
    assert calls == [MAX_RESPONSE_BYTES + 1]


def test_backend_dotenv_is_loaded_without_import_side_effects(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Local only\nGEMINI_API_KEY='local-test-key'\nGEMINI_MODEL=gemini-3.5-flash-lite\nOTHER=ignored\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(extractor, "ENV_FILE", env_file)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    calls = []

    def transport(_body, key, model):
        calls.append((key, model))
        return response('{"evidence":[]}')

    assert analyze_message(MESSAGE, transport=transport)["mode"] == "ai"
    assert calls == [("local-test-key", "gemini-3.5-flash-lite")]


def test_shell_environment_wins_over_backend_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=file-key\nGEMINI_MODEL=file-model\n", encoding="utf-8")
    monkeypatch.setattr(extractor, "ENV_FILE", env_file)
    monkeypatch.setenv("GEMINI_API_KEY", "shell-key")
    monkeypatch.setenv("GEMINI_MODEL", "shell-model")
    calls = []

    def transport(_body, key, model):
        calls.append((key, model))
        return response('{"evidence":[]}')

    assert analyze_message(MESSAGE, transport=transport)["mode"] == "ai"
    assert calls == [("shell-key", "shell-model")]


def test_empty_shell_key_does_not_fall_through_to_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setattr(extractor, "ENV_FILE", env_file)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert analyze_message(MESSAGE, transport=lambda *_: response('{"evidence":[]}'))["mode"] == "fallback"


def test_missing_or_invalid_dotenv_falls_back_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(extractor, "ENV_FILE", tmp_path / "missing.env")
    assert analyze_message(MESSAGE, transport=lambda *_: response('{"evidence":[]}'))["mode"] == "fallback"

    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=oversized\n" + "x" * (extractor.MAX_ENV_FILE_BYTES + 1), encoding="utf-8")
    monkeypatch.setattr(extractor, "ENV_FILE", env_file)
    assert analyze_message(MESSAGE, transport=lambda *_: response('{"evidence":[]}'))["mode"] == "fallback"
