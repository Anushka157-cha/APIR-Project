from __future__ import annotations

import asyncio
import random
from typing import Any, Callable

import httpx


class CircuitOpen(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_seconds: float = 10.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.open_until = 0.0

    def allow(self) -> None:
        now = asyncio.get_event_loop().time()
        if self.open_until and now < self.open_until:
            raise CircuitOpen("circuit breaker open")
        if self.open_until and now >= self.open_until:
            self.failures = 0
            self.open_until = 0.0

    def record_success(self) -> None:
        self.failures = 0
        self.open_until = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.open_until = asyncio.get_event_loop().time() + self.reset_seconds


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 2,
    timeout: float = 5.0,
    breaker: CircuitBreaker | None = None,
    idempotent: bool = True,
    **kwargs: Any,
) -> httpx.Response:
    if breaker:
        breaker.allow()
    last_exc: Exception | None = None
    attempts = retries + 1 if idempotent or method.upper() == "GET" else 1
    for attempt in range(attempts):
        try:
            response = await client.request(method, url, timeout=timeout, **kwargs)
            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    "server error", request=response.request, response=response
                )
            if breaker:
                breaker.record_success()
            return response
        except CircuitOpen:
            raise
        except Exception as exc:
            last_exc = exc
            if breaker:
                breaker.record_failure()
            if attempt == attempts - 1:
                break
            await asyncio.sleep((2**attempt) * 0.05 + random.random() * 0.05)
    assert last_exc is not None
    raise last_exc
