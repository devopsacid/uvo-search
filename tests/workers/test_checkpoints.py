"""Checkpoint semantics: cycle start minus overlap, tz-aware (P7)."""

from datetime import UTC, date, datetime

import fakeredis.aioredis
import httpx
import pytest
import respx
from mongomock_motor import AsyncMongoMockClient

import uvo_workers.crz as crz_mod
import uvo_workers.ted as ted_mod
from uvo_workers.checkpoints import next_checkpoint, resolve_since

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def test_next_checkpoint_is_cycle_start_minus_overlap():
    assert next_checkpoint(NOW, overlap_seconds=3600) == "2026-10-19T11:00:00+00:00"


def test_next_checkpoint_is_timezone_aware():
    parsed = datetime.fromisoformat(next_checkpoint(NOW, overlap_seconds=0))
    assert parsed.tzinfo is not None


def test_resolve_since_parses_stored_checkpoint():
    assert resolve_since("2026-10-01T08:00:00+00:00", recent_days=7, now=NOW) == date(2026, 10, 1)


def test_resolve_since_parses_legacy_naive_checkpoint():
    assert resolve_since("2026-10-01T08:00:00", recent_days=7, now=NOW) == date(2026, 10, 1)


@pytest.mark.parametrize("stored", [None, "", "not-a-date"])
def test_resolve_since_falls_back_to_recent_days(stored):
    assert resolve_since(stored, recent_days=7, now=NOW) == date(2026, 10, 12)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


@pytest.mark.asyncio
async def test_crz_checkpoint_is_cycle_start_minus_overlap(monkeypatch):
    mongo_client = AsyncMongoMockClient()
    monkeypatch.setattr(crz_mod, "AsyncIOMotorClient", lambda *a, **kw: mongo_client)
    monkeypatch.setattr(crz_mod, "datetime", _FrozenDatetime)
    monkeypatch.setattr(crz_mod.get_settings(), "checkpoint_overlap_seconds", 7200)

    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        mock.get("/api/data/crz/contracts/sync").mock(return_value=httpx.Response(200, json=[]))
        await crz_mod._extract(fakeredis.aioredis.FakeRedis(), {})

    doc = await mongo_client["uvo_search"].pipeline_state.find_one({"source": "crz"})
    saved = doc.get("state", doc)["crz_since"]
    assert saved == "2026-10-19T10:00:00+00:00"


@pytest.mark.asyncio
async def test_ted_checkpoint_is_cycle_start_minus_overlap(monkeypatch):
    mongo_client = AsyncMongoMockClient()
    monkeypatch.setattr(ted_mod, "AsyncIOMotorClient", lambda *a, **kw: mongo_client)
    monkeypatch.setattr(ted_mod, "datetime", _FrozenDatetime)
    monkeypatch.setattr(ted_mod.get_settings(), "checkpoint_overlap_seconds", 7200)

    with respx.mock(base_url="https://api.ted.europa.eu") as mock:
        mock.post("/v3/notices/search").mock(
            return_value=httpx.Response(200, json={"notices": [], "totalNoticeCount": 0})
        )
        await ted_mod._extract(fakeredis.aioredis.FakeRedis(), {})

    doc = await mongo_client["uvo_search"].pipeline_state.find_one({"source": "ted"})
    saved = doc.get("state", doc)["ted_since"]
    assert saved == "2026-10-19T10:00:00+00:00"
