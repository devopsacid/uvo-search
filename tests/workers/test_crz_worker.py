"""Tests for uvo_workers.crz — truncated-fetch checkpoint safety (Bug A).

A mid-sync HTTP failure must not be swallowed inside the fetch generator:
doing so let `_extract` reach its `save_checkpoint(..., utcnow())` call as if
the sync had fully completed, silently skipping everything between the
truncation point and "now" on the next cycle. The fix lets the error
propagate out of `fetch_contracts_since` so `_extract` (and `run_extractor_loop`)
never reach the checkpoint save, and the failure is recorded as `cycle_failed`.
"""

import asyncio

import fakeredis.aioredis
import httpx
import pytest
import respx
from mongomock_motor import AsyncMongoMockClient

import uvo_workers.crz as crz_mod
import uvo_workers.runner as runner_mod
from uvo_pipeline.redis_client import RedisSettings
from uvo_workers.runner import run_extractor_loop

BASE_URL = "https://datahub.ekosystem.slovensko.digital"

CONTRACT_1 = {
    "id": 5587100,
    "subject": "Test contract",
    "contracting_authority_name": "City",
    "contracting_authority_cin_raw": "11111111",
    "supplier_name": "Supplier",
    "supplier_cin_raw": "22222222",
    "signed_on": "2024-01-15",
    "contract_price_total_amount": "50000.0",
}


def _fake_redis_settings() -> RedisSettings:
    return RedisSettings(redis_url="redis://localhost:6379/0", redis_password="")


def _mock_truncated_sync(mock: respx.MockRouter) -> None:
    """First page succeeds (yielding one contract); second page 500s."""
    next_url = f"{BASE_URL}/api/data/crz/contracts/sync/page2"
    mock.get("/api/data/crz/contracts/sync").mock(
        return_value=httpx.Response(
            200,
            json=[CONTRACT_1],
            headers={"Link": f'<{next_url}>; rel="next"'},
        )
    )
    mock.get("/api/data/crz/contracts/sync/page2").mock(return_value=httpx.Response(500))


@pytest.mark.asyncio
async def test_crz_extract_raises_and_leaves_checkpoint_untouched(monkeypatch):
    mongo_client = AsyncMongoMockClient()
    monkeypatch.setattr(crz_mod, "AsyncIOMotorClient", lambda *a, **kw: mongo_client)
    fake_redis = fakeredis.aioredis.FakeRedis()

    with respx.mock(base_url=BASE_URL) as mock:
        _mock_truncated_sync(mock)
        with pytest.raises(httpx.HTTPStatusError):
            await crz_mod._extract(fake_redis, {})

    db = mongo_client["uvo_search"]
    checkpoint = await db.pipeline_state.find_one({"source": "crz"})
    assert checkpoint is None


@pytest.mark.asyncio
async def test_crz_worker_cycle_failed_logged_and_checkpoint_untouched(monkeypatch):
    """Driven through the real daemon loop: cycle_failed is logged, and the
    pipeline_state checkpoint for `crz` is never written."""
    mongo_client = AsyncMongoMockClient()
    monkeypatch.setattr(crz_mod, "AsyncIOMotorClient", lambda *a, **kw: mongo_client)
    monkeypatch.setattr(runner_mod, "AsyncIOMotorClient", lambda *a, **kw: mongo_client)

    fake_redis = fakeredis.aioredis.FakeRedis()

    async def fake_get_redis(url=None, password=None):
        return fake_redis

    async def fake_close_redis(client):
        pass

    monkeypatch.setattr(runner_mod, "get_redis", fake_get_redis)
    monkeypatch.setattr(runner_mod, "close_redis", fake_close_redis)

    done = asyncio.Event()
    real_extract = crz_mod._extract

    async def extract_then_signal(redis, state):
        try:
            return await real_extract(redis, state)
        finally:
            done.set()

    with respx.mock(base_url=BASE_URL) as mock:
        _mock_truncated_sync(mock)

        loop_task = asyncio.create_task(
            run_extractor_loop(
                source="crz",
                interval_seconds=1000,
                extract=extract_then_signal,
                redis_settings=_fake_redis_settings(),
                health_port=0,
                instance_id="crz-test",
            )
        )
        await asyncio.wait_for(done.wait(), timeout=5.0)
        loop_task.cancel()
        try:
            await loop_task
        except (asyncio.CancelledError, SystemExit):
            pass

    db = mongo_client["uvo_search"]

    checkpoint = await db.pipeline_state.find_one({"source": "crz"})
    assert checkpoint is None

    failed = await db.ingestion_log.find({"event": "cycle_failed"}).to_list(length=10)
    assert len(failed) == 1
    assert failed[0]["source"] == "crz"
    assert failed[0]["level"] == "error"
    assert "HTTPStatusError" in failed[0]["message"]

    # cycle_complete must never have been logged for this failed cycle
    complete = await db.ingestion_log.find({"event": "cycle_complete"}).to_list(length=10)
    assert complete == []
