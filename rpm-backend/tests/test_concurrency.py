import asyncio
import json

import httpx
import pytest
from conftest import FakeExtractor

from app.extractor import ExtractionEnvelope

BODY = {"messageText": "로그인하세요", "consentToExternalAi": True}


class GateExtractor(FakeExtractor):
    def __init__(self, goal=1):
        super().__init__()
        self.goal = goal
        self.started, self.release = asyncio.Event(), asyncio.Event()

    async def extract(self, message):
        self.calls += 1
        if self.calls >= self.goal:
            self.started.set()
        try:
            await self.release.wait()
            return ExtractionEnvelope("completed", '{"evidence":[]}')
        except asyncio.CancelledError:
            self.cancelled = True
            raise


async def test_four_running_fifth_rejected_without_external_call(factory):
    fake = GateExtractor(goal=4)
    app, _ = factory(fake)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client,
    ):
        tasks = [asyncio.create_task(client.post("/analyze", json=BODY)) for _ in range(4)]
        await asyncio.wait_for(fake.started.wait(), timeout=1)
        rejected = await client.post("/analyze", json=BODY)
        assert rejected.status_code == 503 and rejected.headers["retry-after"] == "3"
        assert fake.calls == 4 and app.state.limits.active == 4
        fake.release.set()
        responses = await asyncio.gather(*tasks)
        assert all(r.status_code == 200 for r in responses)
        assert app.state.limits.active == 0


async def test_cancelled_request_cancels_extractor_and_releases_slot(factory):
    fake = GateExtractor()
    app, _ = factory(fake)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client,
    ):
        task = asyncio.create_task(client.post("/analyze", json=BODY))
        await asyncio.wait_for(fake.started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert fake.cancelled and app.state.limits.active == 0


def scope(headers=None):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/analyze",
        "raw_path": b"/analyze",
        "query_string": b"",
        "headers": headers or [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 10000),
        "server": ("test", 80),
    }


async def test_real_asgi_disconnect_signal(factory):
    fake = GateExtractor()
    app, _ = factory(fake)
    messages = asyncio.Queue()
    await messages.put({"type": "http.request", "body": json.dumps(BODY).encode(), "more_body": False})
    sent = []

    async def send(message):
        sent.append(message)

    async with app.router.lifespan_context(app):
        task = asyncio.create_task(app(scope(), messages.get, send))
        await asyncio.wait_for(fake.started.wait(), timeout=1)
        await messages.put({"type": "http.disconnect"})
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        assert fake.cancelled and app.state.limits.active == 0 and not sent


async def test_chunked_body_stops_at_limit(factory):
    app, fake = factory()
    chunks = asyncio.Queue()
    await chunks.put({"type": "http.request", "body": b" " * 16384, "more_body": True})
    await chunks.put({"type": "http.request", "body": b" " * 16385, "more_body": True})
    sent = []

    async def send(message):
        sent.append(message)

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(app(scope(), chunks.get, send), timeout=1)
    assert sent[0]["status"] == 413 and fake.calls == 0


async def test_clients_never_share_originals(factory):
    class EchoExtractor(FakeExtractor):
        async def extract(self, message):
            await asyncio.sleep(0)
            return ExtractionEnvelope(
                "completed", json.dumps({"evidence": [{"type": "ACT_LINK", "quote": message}]})
            )

    app, _ = factory(EchoExtractor())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client,
    ):
        messages = ["A 링크를 확인하세요", "B 링크를 확인하세요", "C 링크를 확인하세요"]
        results = await asyncio.gather(
            *(client.post("/analyze", json={**BODY, "messageText": m}) for m in messages)
        )
    assert [r.json()["evidence"][0]["quote"] for r in results] == messages
