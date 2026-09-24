"""Atomic, non-awaiting operations within one ASGI event loop; one worker only."""

import math
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass

from .errors import APIError


@dataclass
class Bucket:
    capacity: int
    tokens: float
    updated: float

    def refill(self, now):
        self.tokens = min(self.capacity, self.tokens + max(0, now - self.updated) * self.capacity / 60)
        self.updated = now

    def wait(self):
        return max(0, math.ceil((1 - self.tokens) * 60 / self.capacity))


@dataclass
class ClientBuckets:
    analyze: Bucket
    guidance: Bucket
    last_seen: float


class RequestLimits:
    def __init__(self, settings, *, clock=time.monotonic, ttl=600, max_keys=10000):
        self.settings, self.clock, self.ttl, self.max_keys = settings, clock, ttl, max_keys
        self.clients = OrderedDict()
        now = clock()
        capacity = settings.analyze_global_per_minute
        self.global_bucket = Bucket(capacity, capacity, now)
        self.active = 0

    def _client(self, ip, now):
        while self.clients and next(iter(self.clients.values())).last_seen + self.ttl <= now:
            self.clients.popitem(last=False)
        if ip not in self.clients:
            if len(self.clients) >= self.max_keys:
                raise APIError("RATE_LIMITED", retry_after=60)
            a, g = self.settings.analyze_per_ip_per_minute, self.settings.guidance_per_ip_per_minute
            self.clients[ip] = ClientBuckets(Bucket(a, a, now), Bucket(g, g, now), now)
        item = self.clients[ip]
        item.last_seen = now
        self.clients.move_to_end(ip)
        return item

    def acquire_analysis(self, ip):
        now = self.clock()
        client = self._client(ip, now)
        buckets = (client.analyze, self.global_bucket)
        for bucket in buckets:
            bucket.refill(now)
        delay = max(b.wait() for b in buckets)
        if delay:
            raise APIError("RATE_LIMITED", retry_after=delay)
        if self.active >= self.settings.max_concurrent_analyses:
            raise APIError("SERVICE_BUSY", retry_after=3)
        for bucket in buckets:
            bucket.tokens -= 1
        self.active += 1

    def release_analysis(self):
        if self.active <= 0:
            raise RuntimeError("unbalanced analysis slot")
        self.active -= 1

    @asynccontextmanager
    async def analysis(self, ip):
        self.acquire_analysis(ip)
        try:
            yield
        finally:
            # No await: task cancellation cannot interrupt slot release.
            self.release_analysis()

    def guidance(self, ip):
        now = self.clock()
        bucket = self._client(ip, now).guidance
        bucket.refill(now)
        if bucket.wait():
            raise APIError("RATE_LIMITED", retry_after=bucket.wait())
        bucket.tokens -= 1
