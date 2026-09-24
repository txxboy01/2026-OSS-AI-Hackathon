import pytest

from app.config import Settings
from app.errors import APIError
from app.limits import RequestLimits


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make(**overrides):
    clock = Clock()
    settings = Settings(app_env="test", _env_file=None, **overrides)
    return RequestLimits(settings, clock=clock), clock


def test_refill_and_no_partial_token_consumption():
    limits, clock = make(analyze_global_per_minute=1)
    limits.acquire_analysis("A")
    limits.release_analysis()
    with pytest.raises(APIError, match="RATE_LIMITED"):
        limits.acquire_analysis("B")
    assert limits.clients["B"].analyze.tokens == 5
    clock.now = 60
    limits.acquire_analysis("B")
    limits.release_analysis()
    assert limits.clients["B"].analyze.tokens == 4


def test_busy_does_not_consume_tokens():
    limits, _ = make(max_concurrent_analyses=1)
    limits.acquire_analysis("A")
    before = limits.global_bucket.tokens
    with pytest.raises(APIError, match="SERVICE_BUSY"):
        limits.acquire_analysis("B")
    assert limits.clients["B"].analyze.tokens == 5 and limits.global_bucket.tokens == before
    limits.release_analysis()
    limits.acquire_analysis("B")
    limits.release_analysis()


def test_ip_burst_boundary():
    limits, clock = make()
    for _ in range(5):
        limits.acquire_analysis("A")
        limits.release_analysis()
    with pytest.raises(APIError) as error:
        limits.acquire_analysis("A")
    assert error.value.code == "RATE_LIMITED" and error.value.retry_after == 12
    clock.now = 11.99
    with pytest.raises(APIError):
        limits.acquire_analysis("A")
    clock.now = 12
    limits.acquire_analysis("A")
    limits.release_analysis()


def test_guidance_independent_bucket():
    limits, clock = make()
    for _ in range(30):
        limits.guidance("A")
    with pytest.raises(APIError, match="RATE_LIMITED"):
        limits.guidance("A")
    limits.acquire_analysis("A")
    limits.release_analysis()
    clock.now = 2
    limits.guidance("A")


def test_bounded_keys_ttl_and_restarts():
    limits, clock = make()
    limits.max_keys = 1
    limits.guidance("A")
    with pytest.raises(APIError, match="RATE_LIMITED"):
        limits.guidance("B")
    clock.now = 600
    limits.guidance("B")
    assert list(limits.clients) == ["B"]
    fresh, _ = make()
    assert not fresh.clients and fresh.active == 0


async def test_exception_slot_release():
    limits, _ = make()
    with pytest.raises(RuntimeError):
        async with limits.analysis("A"):
            raise RuntimeError("synthetic")
    assert limits.active == 0
