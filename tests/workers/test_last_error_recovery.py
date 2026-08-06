"""last_error must reflect the *last* cycle, not "any cycle ever this
process lifetime" — otherwise a single transient failure marks /readyz
unready until the pod restarts (PR #23 wires readiness probes to /readyz).

Runs the real run_ingestor / run_dedup_worker loops with dependencies
monkeypatched at the module level, mirroring the existing pattern in
tests/workers/test_runner.py.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from mongomock_motor import AsyncMongoMockClient

import uvo_workers.dedup as dedup_mod
import uvo_workers.ingestor as ingestor_mod


class _FakeNeo4jSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeNeo4jDriver:
    def session(self):
        return _FakeNeo4jSession()

    async def close(self):
        pass


class _FakeGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        return _FakeNeo4jDriver()


def _encoded_entry(entry_id: bytes = b"1-0") -> tuple:
    payload = {
        "source": "vestnik",
        "source_id": "V-1",
        "notice_type": "contract_award",
        "title": "Test notice",
    }
    fields = {
        b"payload": json.dumps(payload).encode(),
        b"hash": b"h",
        b"run": b"r",
    }
    return (entry_id, fields)


async def _never_returns() -> None:
    await asyncio.Event().wait()


async def _publish_until(
    fake_redis, channel: str, message: str, signal: asyncio.Event, *, timeout: float = 10
) -> None:
    """Pub/sub (fakeredis included) never buffers for a not-yet-subscribed
    listener, so a single publish right after starting the worker task races
    the worker's own subscribe call. Retry the publish until `signal` fires."""
    async with asyncio.timeout(timeout):
        while not signal.is_set():
            await fake_redis.publish(channel, message)
            await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_ingestor_last_error_clears_after_next_successful_batch(monkeypatch):
    fake_redis = fakeredis.aioredis.FakeRedis()

    monkeypatch.setattr(ingestor_mod, "AsyncIOMotorClient", AsyncMongoMockClient)
    monkeypatch.setattr(ingestor_mod, "get_redis", AsyncMock(return_value=fake_redis))
    monkeypatch.setattr(ingestor_mod, "close_redis", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "AsyncGraphDatabase", _FakeGraphDatabase)
    monkeypatch.setattr(ingestor_mod, "ensure_consumer_group", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "ensure_constraints", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "merge_notice_batch", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "ack", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "publish", AsyncMock())
    # upsert_batch is exercised thoroughly elsewhere (tests/pipeline/loaders/
    # test_mongo.py); this test is only about the last_error metric, so stub
    # it to a plain success and avoid coupling to mongomock-motor's bulk_write
    # shim.
    monkeypatch.setattr(ingestor_mod, "upsert_batch", AsyncMock(return_value={}))
    # autoclaim_stale runs a real XAUTOCLAIM against fake_redis every time
    # read_group comes back empty; stub it out so the test isn't coupled to
    # fakeredis's stream-command support.
    monkeypatch.setattr(ingestor_mod, "autoclaim_stale", AsyncMock(return_value=[]))

    call_count = [0]
    # Gate cycle 2 behind an explicit event so the test can deterministically
    # observe the post-cycle-1-failure state before cycle 2 is allowed to
    # proceed and clear it — avoids a race between the assertion and the
    # (very fast, in-memory) cycle 2 completing before we get to check.
    reached_cycle2 = asyncio.Event()
    proceed_cycle2 = asyncio.Event()

    async def fake_read_group(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("transient redis blip")
        if call_count[0] == 2:
            reached_cycle2.set()
            await proceed_cycle2.wait()
            return [("notices:vestnik", [_encoded_entry()])]
        await asyncio.sleep(0.01)
        return []

    monkeypatch.setattr(ingestor_mod, "read_group", fake_read_group)

    captured: dict = {}

    async def fake_serve_health(port, snapshot, **kwargs):
        captured["snapshot"] = snapshot
        await _never_returns()

    monkeypatch.setattr(ingestor_mod, "serve_health", fake_serve_health)

    task = asyncio.create_task(ingestor_mod.run_ingestor())
    try:
        # Cycle 1's exception is caught (and last_error set) strictly before
        # the loop calls read_group a second time, so this wait is a
        # happens-before guarantee, not a poll-and-hope.
        await asyncio.wait_for(reached_cycle2.wait(), timeout=10)
        assert captured["snapshot"]()["last_error"] is not None

        proceed_cycle2.set()

        # Cycle 2 (the batch write) succeeds — last_error must clear.
        for _ in range(200):
            if captured["snapshot"]()["last_error"] is None:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("last_error never cleared after a successful batch")
        assert captured["snapshot"]()["last_error"] is None
    finally:
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError, SystemExit):
            pass


@pytest.mark.asyncio
async def test_dedup_worker_last_error_clears_after_next_successful_run(monkeypatch):
    """Trigger cycles via real notices:written publishes (the debounce path),
    not a zero-second dedup_interval_seconds: with every dependency mocked to
    resolve instantly, a zero interval makes the interval-tick branch a tight
    loop that never genuinely suspends (mocked awaits don't yield to the
    event loop the way real I/O does), starving the test's own coroutine and
    task.cancel()'s delivery — an artifact of over-mocking, not something
    that can happen in production where real I/O always yields.
    """
    fake_redis = fakeredis.aioredis.FakeRedis()

    monkeypatch.setattr(dedup_mod, "AsyncIOMotorClient", AsyncMongoMockClient)
    monkeypatch.setattr(dedup_mod, "get_redis", AsyncMock(return_value=fake_redis))
    monkeypatch.setattr(dedup_mod, "close_redis", AsyncMock())
    monkeypatch.setattr(dedup_mod, "recompute_entity_stats", AsyncMock(return_value={}))
    # A failed cycle still counts against MIN_DEDUP_INTERVAL_SECONDS (it sets
    # last_dedup_run before calling _run_dedup), so with the real 300s floor
    # cycle 2 wouldn't fire for 5 minutes. Shrink it so the test is fast.
    monkeypatch.setattr(dedup_mod, "MIN_DEDUP_INTERVAL_SECONDS", 0.05)

    call_count = [0]
    reached_cycle1 = asyncio.Event()
    reached_cycle2 = asyncio.Event()

    async def fake_run_cross_source_dedup(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            reached_cycle1.set()
            raise RuntimeError("transient mongo blip")
        reached_cycle2.set()
        return 0

    monkeypatch.setattr(dedup_mod, "run_cross_source_dedup", fake_run_cross_source_dedup)

    captured: dict = {}

    async def fake_serve_health(port, snapshot, **kwargs):
        captured["snapshot"] = snapshot
        await _never_returns()

    monkeypatch.setattr(dedup_mod, "serve_health", fake_serve_health)

    # Debounce fires immediately; the (default, real) interval fallback is
    # 3600s and never fires in this test.
    monkeypatch.setattr(
        dedup_mod, "get_settings", lambda: dedup_mod.DedupWorkerSettings(dedup_debounce_seconds=0)
    )

    task = asyncio.create_task(dedup_mod.run_dedup_worker())
    try:
        await _publish_until(fake_redis, "notices:written", "1", reached_cycle1)

        # Cycle 1's exception is caught (and last_error set) strictly before
        # fake_run_cross_source_dedup returns, so this is a happens-before
        # guarantee, not a poll-and-hope.
        assert captured["snapshot"]()["last_error"] is not None

        await _publish_until(fake_redis, "notices:written", "2", reached_cycle2)

        for _ in range(200):
            if captured["snapshot"]()["last_error"] is None:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("last_error never cleared after a successful dedup run")
        assert captured["snapshot"]()["last_error"] is None
    finally:
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError, SystemExit):
            pass
