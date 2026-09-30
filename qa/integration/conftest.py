"""FE(Next.js) ↔ BE(FastAPI) 통합 테스트 공용 설정.

FE 소스(page.tsx)에서 실제로 보내는 요청 형태·샘플·행동 값을 읽어 와서
실제 BE 앱(create_app)에 그대로 보낸다. Gemini 호출만 가짜 추출기로 대체한다.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "rpm-backend"
sys.path.insert(0, str(BACKEND))

from app.config import Settings  # noqa: E402
from app.errors import ExtractionFailure  # noqa: E402
from app.extractor import ExtractionEnvelope  # noqa: E402
from app.main import create_app  # noqa: E402

# 다른 브랜치의 page.tsx로 검증하려면 RPM_FE_PAGE 환경변수로 경로를 지정한다.
FE_PAGE = Path(os.environ.get("RPM_FE_PAGE", REPO / "frontend/src/app/page.tsx"))
FE_ORIGINS = os.environ.get("RPM_FE_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")


class FakeExtractor:
    """Gemini 대신 정해진 결과를 돌려주는 추출기."""

    def __init__(self, evidence=None, error=None, delay=0):
        self.evidence, self.error, self.delay = evidence or [], error, delay
        self.messages = []

    async def extract(self, message):
        import asyncio

        self.messages.append(message)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return ExtractionEnvelope("completed", json.dumps({"evidence": self.evidence}, ensure_ascii=False))

    async def aclose(self):
        pass


class FrontendSource:
    """page.tsx에서 FE↔BE 계약에 해당하는 부분만 정규식으로 뽑아낸다."""

    def __init__(self, path):
        self.text = path.read_text(encoding="utf-8")

    def _union(self, type_name):
        match = re.search(rf"type {type_name} = ([^;]+);", self.text)
        return re.findall(r'"(\w+)"', match.group(1)) if match else []

    def _object_keys(self, type_name):
        match = re.search(rf"type {type_name} = \{{(.*?)\}};", self.text, re.S)
        if not match:
            return []
        body = match.group(1)
        while re.search(r"\{[^{}]*\}", body):  # 중첩 객체 타입은 제외하고 최상위 키만
            body = re.sub(r"\{[^{}]*\}", "", body)
        return re.findall(r"(\w+)\??:", body)

    @property
    def endpoints(self):
        return re.findall(r"fetch\(`\$\{API_BASE_URL\}(/\w+)`", self.text)

    @property
    def api_env_vars(self):
        return set(re.findall(r"process\.env\.(NEXT_PUBLIC_\w+)", self.text))

    def request_keys(self, endpoint):
        match = re.search(rf"{re.escape(endpoint)}`.*?JSON\.stringify\(\{{(.*?)\}}\)", self.text, re.S)
        return re.findall(r"(?:^|,)\s*(\w+)", match.group(1).strip()) if match else []

    @property
    def samples(self):
        return dict(re.findall(r"(\w+): \{ name: \"[^\"]+\", text: `([^`]*)`", self.text))

    @property
    def ui_actions(self):
        return re.findall(r"\{ value: \"(\w+)\", label:", self.text)

    user_action_type = property(lambda self: self._union("UserAction"))
    analyze_statuses = property(lambda self: self._union("AnalyzeResponse"))
    analyze_keys = property(lambda self: self._object_keys("AnalyzeResponse"))
    evidence_keys = property(lambda self: self._object_keys("Evidence"))
    guidance_keys = property(lambda self: self._object_keys("GuidanceResponse"))


@pytest.fixture(scope="session")
def fe():
    if not FE_PAGE.exists():
        pytest.skip(f"FE 소스 없음: {FE_PAGE}")
    source = FrontendSource(FE_PAGE)
    if "/analyze" not in source.endpoints:
        pytest.skip("이 브랜치의 page.tsx에 API 연동 코드가 없음 (feature/fe-api-integration 머지 전)")
    return source


@pytest.fixture
def make_client():
    """가짜 추출기를 주입한 실제 BE 앱의 TestClient를 만든다."""
    clients = []

    def make(extractor=None, **overrides):
        settings = Settings(_env_file=None, app_env="test", cors_allow_origins=FE_ORIGINS, **overrides)
        client = TestClient(create_app(settings, extractor or FakeExtractor()), raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def fe_post(client, path, body, origin=FE_ORIGINS[0]):
    """FE의 fetch와 같은 헤더로 요청한다."""
    return client.post(path, json=body, headers={"Content-Type": "application/json", "Origin": origin})


__all__ = ["ExtractionFailure", "FakeExtractor", "fe_post", "FE_ORIGINS", "REPO", "BACKEND"]
