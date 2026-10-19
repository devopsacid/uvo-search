"""MCP exposes /metrics and keeps uvo_ready{service="uvo-mcp"} fresh."""

from unittest.mock import AsyncMock, MagicMock

from prometheus_client import REGISTRY

from uvo_mcp import server


def _ready() -> float | None:
    return REGISTRY.get_sample_value("uvo_ready", {"service": "uvo-mcp"})


async def test_metrics_endpoint_serves_default_registry():
    await server.refresh_ready()
    response = await server.metrics_endpoint(MagicMock())
    assert response.status_code == 200
    assert response.media_type.startswith("text/plain")
    assert b"uvo_ready" in response.body


async def test_refresh_ready_sets_gauge_from_mongo_and_index_probe(monkeypatch):
    db = MagicMock()
    db.command = AsyncMock(return_value={"ok": 1})
    probe = MagicMock()
    probe.ready = AsyncMock(return_value=True)
    monkeypatch.setitem(server._runtime, "mongo_db", db)
    monkeypatch.setitem(server._runtime, "index_probe", probe)
    await server.refresh_ready()
    assert _ready() == 1


async def test_refresh_ready_is_zero_without_mongo(monkeypatch):
    monkeypatch.setitem(server._runtime, "mongo_db", None)
    await server.refresh_ready()
    assert _ready() == 0
