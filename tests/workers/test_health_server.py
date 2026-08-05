"""The health server must distinguish liveness from readiness."""

import asyncio
import json

import pytest

from uvo_workers.health import default_is_ready, serve_health


def test_default_is_ready_true_when_connected():
    assert default_is_ready({"redis_connected": True, "last_error": None}) is True


def test_default_is_ready_false_when_redis_down():
    assert default_is_ready({"redis_connected": False, "last_error": None}) is False


def test_default_is_ready_false_when_error_present():
    assert default_is_ready({"redis_connected": True, "last_error": "ConnectionError"}) is False


async def _request(port: int, path: str) -> tuple[int, dict]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
    await writer.drain()
    raw = await reader.read(65536)
    writer.close()
    head, _, body = raw.partition(b"\r\n\r\n")
    status = int(head.split()[1])
    return status, json.loads(body) if body else {}


@pytest.mark.asyncio
async def test_healthz_is_200_even_when_not_ready():
    """Liveness must not fail on a dependency blip, or k8s restart-loops the pod."""
    metrics = {"redis_connected": False, "last_error": "boom"}
    server = asyncio.create_task(serve_health(18099, lambda: dict(metrics)))
    await asyncio.sleep(0.1)
    try:
        status, _ = await _request(18099, "/healthz")
        assert status == 200
    finally:
        server.cancel()


@pytest.mark.asyncio
async def test_readyz_is_503_when_not_ready():
    metrics = {"redis_connected": False, "last_error": "boom"}
    server = asyncio.create_task(serve_health(18098, lambda: dict(metrics)))
    await asyncio.sleep(0.1)
    try:
        status, body = await _request(18098, "/readyz")
        assert status == 503
        assert body["redis_connected"] is False
    finally:
        server.cancel()


@pytest.mark.asyncio
async def test_readyz_is_200_when_ready():
    metrics = {"redis_connected": True, "last_error": None}
    server = asyncio.create_task(serve_health(18097, lambda: dict(metrics)))
    await asyncio.sleep(0.1)
    try:
        status, _ = await _request(18097, "/readyz")
        assert status == 200
    finally:
        server.cancel()
