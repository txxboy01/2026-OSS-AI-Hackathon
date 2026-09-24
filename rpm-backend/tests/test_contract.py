from pathlib import Path

import pytest
import yaml
from conftest import FakeExtractor, envelope
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate as validate_openapi
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from app.extractor import ExtractionEnvelope

CONTRACT = yaml.safe_load((Path(__file__).parent.parent / "docs/openapi-v1.yaml").read_text())
REGISTRY = Registry().with_resource("urn:rpm-contract", Resource(CONTRACT, DRAFT202012))


def schema_check(name, value):
    validator = Draft202012Validator(
        {"$ref": f"urn:rpm-contract#/components/schemas/{name}"},
        registry=REGISTRY,
        format_checker=FormatChecker(),
    )
    validator.validate(value)


def test_entire_openapi_document_valid():
    validate_openapi(CONTRACT)


def test_all_contract_examples_are_valid():
    for path in CONTRACT["paths"].values():
        for operation in path.values():
            if "requestBody" in operation:
                body = operation["requestBody"]["content"]["application/json"]
                name = body["schema"]["$ref"].split("/")[-1]
                schema_check(name, body["example"])
            for response in operation["responses"].values():
                content = response["content"]["application/json"]
                name = content["schema"]["$ref"].split("/")[-1]
                for example in content.get("examples", {}).values():
                    schema_check(name, example["value"])


@pytest.mark.parametrize(
    "raw",
    [
        envelope([]),
        envelope([{"type": "ACT_LOGIN", "quote": "로그인하세요"}]),
        envelope([{"type": "ACT_APP", "quote": "없음"}]),
        ExtractionEnvelope("blocked"),
    ],
)
def test_actual_response_variants_follow_contract(factory, raw):
    app, _ = factory(FakeExtractor(raw))
    with TestClient(app) as client:
        schema_check("HealthResponse", client.get("/health").json())
        response = client.post("/analyze", json={"messageText": "로그인하세요", "consentToExternalAi": True})
        assert response.status_code == 200
        schema_check("AnalyzeResponse", response.json())
        schema_check(
            "GuidanceResponse",
            client.post("/guidance", json={"actions": ["SENT_MONEY", "INSTALLED_APP"]}).json(),
        )
        schema_check("ErrorResponse", client.post("/analyze", json={}).json())
        schema_check(
            "ErrorResponse",
            client.post(
                "/analyze", json={"messageText": "인증번호 123456", "consentToExternalAi": True}
            ).json(),
        )


def test_no_user_data_files_or_database_created(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c, _ = client
    before = set(tmp_path.rglob("*"))
    c.post("/analyze", json={"messageText": "로그인하세요", "consentToExternalAi": True})
    c.post("/guidance", json={"actions": ["SENT_MONEY"]})
    assert set(tmp_path.rglob("*")) == before


def test_forwarded_header_is_not_trusted_by_app(client):
    c, fake = client
    for i in range(5):
        assert (
            c.post(
                "/analyze",
                json={"messageText": "로그인하세요", "consentToExternalAi": True},
                headers={"X-Forwarded-For": f"192.0.2.{i + 1}"},
            ).status_code
            == 200
        )
    assert (
        c.post(
            "/analyze",
            json={"messageText": "로그인하세요", "consentToExternalAi": True},
            headers={"X-Forwarded-For": "192.0.2.100"},
        ).status_code
        == 429
    )
    assert fake.calls == 5
