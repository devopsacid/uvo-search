"""fetch_with_retry: backoff + jitter, Retry-After, 5xx/timeout retry."""

import httpx
import pytest

from uvo_pipeline.utils.http_retry import fetch_with_retry, parse_retry_after


def _resp(status: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, request=httpx.Request("GET", "http://x"))


class _Script:
    """Callable returning scripted responses / raising scripted exceptions."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Sleeps:
    def __init__(self):
        self.delays: list[float] = []

    async def __call__(self, seconds: float):
        self.delays.append(seconds)


async def test_returns_immediately_on_success():
    request = _Script(_resp(200))
    sleeps = _Sleeps()

    resp = await fetch_with_retry(request, sleep=sleeps)

    assert resp.status_code == 200
    assert request.calls == 1
    assert sleeps.delays == []


async def test_non_retryable_status_is_returned_not_retried():
    request = _Script(_resp(404))
    resp = await fetch_with_retry(request, sleep=_Sleeps())
    assert resp.status_code == 404
    assert request.calls == 1


async def test_retries_5xx_then_succeeds():
    request = _Script(_resp(503), _resp(502), _resp(200))
    sleeps = _Sleeps()

    resp = await fetch_with_retry(request, sleep=sleeps, jitter=lambda: 1.0, base_delay=1.0)

    assert resp.status_code == 200
    assert request.calls == 3
    assert sleeps.delays == [1.0, 2.0]  # exponential, jitter pinned to 1.0


async def test_retries_timeouts_and_connect_errors():
    request = _Script(httpx.ReadTimeout("t"), httpx.ConnectError("c"), _resp(200))
    resp = await fetch_with_retry(request, sleep=_Sleeps())
    assert resp.status_code == 200
    assert request.calls == 3


async def test_honours_retry_after_seconds():
    request = _Script(_resp(429, {"Retry-After": "7"}), _resp(200))
    sleeps = _Sleeps()

    await fetch_with_retry(request, sleep=sleeps, jitter=lambda: 0.0)

    assert sleeps.delays == [7.0]


async def test_backoff_is_capped():
    request = _Script(*[_resp(500)] * 5, _resp(200))
    sleeps = _Sleeps()

    await fetch_with_retry(
        request, sleep=sleeps, jitter=lambda: 1.0, base_delay=10.0, max_delay=15.0, max_attempts=6
    )

    assert max(sleeps.delays) == 15.0


async def test_exhausted_retries_raise_status_error():
    request = _Script(_resp(503), _resp(503), _resp(503))
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_with_retry(request, sleep=_Sleeps(), max_attempts=3)
    assert request.calls == 3


async def test_exhausted_retries_reraise_transport_error():
    request = _Script(httpx.ReadTimeout("a"), httpx.ReadTimeout("b"))
    with pytest.raises(httpx.ReadTimeout):
        await fetch_with_retry(request, sleep=_Sleeps(), max_attempts=2)


def test_parse_retry_after_variants():
    assert parse_retry_after("12") == 12.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("garbage") is None
    assert parse_retry_after("-3") == 0.0
