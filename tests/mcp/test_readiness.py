"""MCP /readyz is a bounded Mongo probe; /health stays unconditional (A20)."""

import json
from unittest.mock import AsyncMock, MagicMock

from uvo_mcp import server


async def test_readyz_503_without_mongo_handle(monkeypatch):
    monkeypatch.setitem(server._runtime, "mongo_db", None)
    response = await server.readiness_check(MagicMock())
    assert response.status_code == 503


def _probe(ready: bool):
    probe = MagicMock()
    probe.ready = AsyncMock(return_value=ready)
    return probe


async def test_readyz_200_when_ping_ok(monkeypatch):
    db = MagicMock()
    db.command = AsyncMock(return_value={"ok": 1})
    monkeypatch.setitem(server._runtime, "mongo_db", db)
    monkeypatch.setitem(server._runtime, "index_probe", _probe(True))
    response = await server.readiness_check(MagicMock())
    assert response.status_code == 200
    assert json.loads(response.body)["status"] == "ready"


async def test_readyz_503_when_ping_fails(monkeypatch):
    db = MagicMock()
    db.command = AsyncMock(side_effect=RuntimeError("down"))
    monkeypatch.setitem(server._runtime, "mongo_db", db)
    assert (await server.readiness_check(MagicMock())).status_code == 503


async def test_readyz_503_when_required_search_indexes_missing(monkeypatch):
    db = MagicMock()
    db.command = AsyncMock(return_value={"ok": 1})
    monkeypatch.setitem(server._runtime, "mongo_db", db)
    monkeypatch.setitem(server._runtime, "index_probe", _probe(False))
    assert (await server.readiness_check(MagicMock())).status_code == 503


async def test_health_ignores_mongo(monkeypatch):
    monkeypatch.setitem(server._runtime, "mongo_db", None)
    response = await server.health_check(MagicMock())
    assert response.status_code == 200
