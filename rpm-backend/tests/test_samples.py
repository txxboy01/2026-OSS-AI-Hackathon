import json
from pathlib import Path

from conftest import FakeExtractor, envelope
from fastapi.testclient import TestClient

from app.redactor import detect_sensitive

ROOT = Path(__file__).parent.parent


def test_all_three_demo_samples_use_real_validation(factory):
    samples = json.loads((ROOT / "samples/messages.json").read_text(encoding="utf-8"))
    expectations = {
        e["id"]: e for e in json.loads((ROOT / "tests/fixtures/expected_samples.json").read_text(encoding="utf-8"))
    }
    assert len(samples) == 3
    for sample in samples:
        assert detect_sensitive(sample["messageText"]) == []
        expected = expectations[sample["id"]]
        app, fake = factory(FakeExtractor(envelope(expected["evidence"])))
        with TestClient(app) as client:
            data = client.post(
                "/analyze", json={"messageText": sample["messageText"], "consentToExternalAi": True}
            ).json()
            assert data["status"] == "VERIFIED"
            assert {e["type"] for e in data["evidence"]} == set(expected["requiredTypes"])
            assert fake.calls == 1


def test_gold_cases_are_synthetic_and_complete():
    cases = json.loads((ROOT / "tests/fixtures/gold_cases.json").read_text(encoding="utf-8"))
    assert len(cases) == 7 and len({c["id"] for c in cases}) == 7
    assert all(not detect_sensitive(c["messageText"]) for c in cases)
    refund = next(c for c in cases if c["id"] == "SAMPLE_REFUND")
    assert "ACT_PAYMENT" not in refund["requiredTypes"]
