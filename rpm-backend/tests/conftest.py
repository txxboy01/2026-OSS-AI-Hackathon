import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.extractor import ExtractionEnvelope
from app.main import create_app


class FakeExtractor:
    def __init__(self, result=None, error=None, delay=0):
        self.result = result or ExtractionEnvelope("completed", '{"evidence":[]}')
        self.error, self.delay = error, delay
        self.calls, self.closed, self.cancelled = 0, False, False
        self.messages = []

    async def extract(self, message):
        self.calls += 1
        self.messages.append(message)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.error:
                raise self.error
            return self.result
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def aclose(self):
        self.closed = True


def envelope(items):
    return ExtractionEnvelope("completed", json.dumps({"evidence": items}, ensure_ascii=False))


@pytest.fixture
def factory():
    def make(fake=None, **overrides):
        settings = Settings(_env_file=None, app_env="test", **overrides)
        fake = fake or FakeExtractor()
        app = create_app(settings, fake)
        return app, fake

    return make


@pytest.fixture
def client(factory):
    app, fake = factory()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, fake


def pytest_make_parametrize_id(config, val, argname):
    if isinstance(val, (str, bytes)) and len(val) > 70:
        return f"{argname}-{len(val)}-chars"
    return None
