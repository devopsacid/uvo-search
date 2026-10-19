"""Ingestor delivery guarantees: partial-failure acks, periodic reclaim,
delivery-count escalation and dead-lettering (P1, P3, P13)."""

import asyncio
import json
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from mongomock_motor import AsyncMongoMockClient

import uvo_workers.ingestor as ingestor_mod
from uvo_pipeline.streams import ensure_consumer_group, read_group, xadd_many
from uvo_workers.ingestor import (
    DEAD_LETTER_STREAM,
    IngestorContext,
    IngestorSettings,
    is_due,
    process_entries,
    reclaim_pending,
    run_maintenance,
)

STREAM = "notices:vestnik"
GROUP = "ingestor"


class _FakeNeo4jSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeNeo4jDriver:
    def session(self):
        return _FakeNeo4jSession()


def _payload(source_id: str) -> dict:
    return {
        "source": "vestnik",
        "source_id": source_id,
        "notice_type": "contract_award",
        "title": f"Notice {source_id}",
        "content_hash": f"h-{source_id}",
        "pipeline_run_id": "run-1",
    }


@pytest.fixture
async def ctx(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis()
    db = AsyncMongoMockClient()["ingestor_test"]
    monkeypatch.setattr(ingestor_mod, "publish", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "upsert_batch", AsyncMock(return_value={"failed": []}))
    monkeypatch.setattr(ingestor_mod, "merge_notice_batch", AsyncMock(return_value={"failed": []}))
    await ensure_consumer_group(redis, STREAM, GROUP)
    yield IngestorContext(
        db=db,
        redis=redis,
        neo4j_driver=_FakeNeo4jDriver(),
        instance_id="inst-1",
        metrics={"batches_processed": 0, "notices_written": 0, "last_error": None},
    )
    await redis.aclose()


async def _deliver(ctx, *source_ids: str):
    """XADD notices and read them as a consumer so they sit in the PEL."""
    await xadd_many(ctx.redis, "vestnik", [_payload(s) for s in source_ids])
    got = await read_group(ctx.redis, GROUP, "c1", [STREAM], count=100, block_ms=None)
    return got[0][1]


async def _pending(ctx) -> int:
    return (await ctx.redis.xpending(STREAM, GROUP))["pending"]


def _settings(**overrides) -> IngestorSettings:
    base = dict(ingestor_reclaim_min_idle_ms=0, ingestor_max_deliveries=3)
    base.update(overrides)
    return IngestorSettings(**base)


# --- P1: partial failures ----------------------------------------------------


async def test_all_ok_acks_everything_and_updates_metrics(ctx):
    entries = await _deliver(ctx, "A", "B")

    outcome = await process_entries(ctx, STREAM, entries)

    assert len(outcome.succeeded) == 2
    assert outcome.failed == [] and outcome.error is None
    assert await _pending(ctx) == 0
    assert ctx.metrics["notices_written"] == 2
    assert ctx.metrics["last_error"] is None
    assert ctx.metrics["last_success_at"] is not None


async def test_mongo_partial_failure_acks_only_successes(ctx, monkeypatch):
    monkeypatch.setattr(
        ingestor_mod, "upsert_batch", AsyncMock(return_value={"failed": [("vestnik", "B")]})
    )
    entries = await _deliver(ctx, "A", "B", "C")

    outcome = await process_entries(ctx, STREAM, entries)

    assert len(outcome.succeeded) == 2
    assert [eid for eid, _ in outcome.failed] == [entries[1][0]]
    pending = await ctx.redis.xpending_range(STREAM, GROUP, min="-", max="+", count=10)
    assert [p["message_id"] for p in pending] == [entries[1][0]]
    assert ctx.metrics["notices_written"] == 2
    assert "failed to write" in ctx.metrics["last_error"]
    ingestor_mod.publish.assert_awaited_once()
    assert ingestor_mod.publish.await_args.args[2]["count"] == 2


async def test_neo4j_only_receives_mongo_successes_and_its_failures_stay_pending(ctx, monkeypatch):
    monkeypatch.setattr(
        ingestor_mod, "upsert_batch", AsyncMock(return_value={"failed": [("vestnik", "A")]})
    )
    merge = AsyncMock(return_value={"failed": [("vestnik", "C")]})
    monkeypatch.setattr(ingestor_mod, "merge_notice_batch", merge)
    entries = await _deliver(ctx, "A", "B", "C")

    outcome = await process_entries(ctx, STREAM, entries)

    merged_ids = [n.source_id for n in merge.await_args.args[1]]
    assert merged_ids == ["B", "C"]
    assert outcome.succeeded == [entries[1][0]]
    assert await _pending(ctx) == 2


async def test_whole_batch_exception_acks_nothing(ctx, monkeypatch):
    monkeypatch.setattr(ingestor_mod, "upsert_batch", AsyncMock(side_effect=RuntimeError("down")))
    entries = await _deliver(ctx, "A", "B")

    outcome = await process_entries(ctx, STREAM, entries)

    assert isinstance(outcome.error, RuntimeError)
    assert outcome.succeeded == []
    assert await _pending(ctx) == 2
    assert ctx.metrics["last_error"] == "RuntimeError"
    event = await ctx.db.ingestion_log.find_one({"event": "write_failed"})
    assert event is not None


# --- P3: reclaim, delivery counts, dead-letter ---------------------------------


async def test_reclaim_retries_stale_entries_below_the_delivery_limit(ctx):
    await _deliver(ctx, "A", "B")

    reclaimed = await reclaim_pending(ctx, _settings(), "c2")

    assert reclaimed == 2
    assert await _pending(ctx) == 0
    assert await ctx.redis.xlen(DEAD_LETTER_STREAM) == 0


async def test_over_limit_entry_is_processed_alone_and_dead_lettered_if_it_still_fails(
    ctx, monkeypatch
):
    async def upsert(db, notices):
        return {
            "failed": [("vestnik", "POISON")]
            if any(n.source_id == "POISON" for n in notices)
            else []
        }

    monkeypatch.setattr(ingestor_mod, "upsert_batch", upsert)
    await _deliver(ctx, "GOOD", "POISON")
    # Two prior reclaims -> delivery count 3 == limit.
    for consumer in ("c2", "c3"):
        await ingestor_mod.autoclaim_stale(ctx.redis, STREAM, GROUP, consumer, min_idle_ms=0)

    await reclaim_pending(ctx, _settings(ingestor_max_deliveries=3), "c4")

    assert await _pending(ctx) == 0, "good entry written, poison entry parked and acked"
    dead = await ctx.redis.xrange(DEAD_LETTER_STREAM)
    assert len(dead) == 1
    assert json.loads(dead[0][1][b"payload"])["source_id"] == "POISON"
    assert b"after" in dead[0][1][b"error"]
    event = await ctx.db.ingestion_log.find_one({"event": "entry_dead_lettered"})
    assert event is not None and event["source"] == "vestnik"
    assert ctx.metrics["notices_written"] >= 1


async def test_dependency_outage_does_not_dead_letter_good_entries(ctx, monkeypatch):
    """When *every* over-limit entry fails alone, it is an outage, not poison."""
    monkeypatch.setattr(
        ingestor_mod,
        "upsert_batch",
        AsyncMock(
            side_effect=lambda db, notices: {"failed": [(n.source, n.source_id) for n in notices]}
        ),
    )
    await _deliver(ctx, "A", "B", "C")
    for consumer in ("c2", "c3"):
        await ingestor_mod.autoclaim_stale(ctx.redis, STREAM, GROUP, consumer, min_idle_ms=0)

    await reclaim_pending(ctx, _settings(ingestor_max_deliveries=3), "c4")

    assert await ctx.redis.xlen(DEAD_LETTER_STREAM) == 0
    assert await _pending(ctx) == 3


async def test_single_entry_infrastructure_error_is_never_dead_lettered(ctx, monkeypatch):
    monkeypatch.setattr(ingestor_mod, "upsert_batch", AsyncMock(side_effect=RuntimeError("down")))
    await _deliver(ctx, "A")
    for consumer in ("c2", "c3"):
        await ingestor_mod.autoclaim_stale(ctx.redis, STREAM, GROUP, consumer, min_idle_ms=0)

    await reclaim_pending(ctx, _settings(ingestor_max_deliveries=3), "c4")

    assert await ctx.redis.xlen(DEAD_LETTER_STREAM) == 0
    assert await _pending(ctx) == 1


def test_is_due():
    assert is_due(None, 100.0, 30.0)
    assert not is_due(90.0, 100.0, 30.0)
    assert is_due(60.0, 100.0, 30.0)


async def test_run_loop_reclaims_even_when_traffic_never_stops(monkeypatch):
    """read_group always returns data, so the old 'only reclaim when idle'
    logic would never reclaim. The timer-based reclaim must still fire."""
    redis = fakeredis.aioredis.FakeRedis()
    entry = (
        b"1-0",
        {b"payload": json.dumps(_payload("A")).encode(), b"hash": b"h", b"run": b"r"},
    )

    monkeypatch.setattr(ingestor_mod, "AsyncIOMotorClient", AsyncMongoMockClient)
    monkeypatch.setattr(ingestor_mod, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(ingestor_mod, "close_redis", AsyncMock())
    monkeypatch.setattr(
        ingestor_mod,
        "AsyncGraphDatabase",
        type("G", (), {"driver": staticmethod(lambda *a, **k: _Driver())}),
    )
    monkeypatch.setattr(ingestor_mod, "ensure_consumer_group", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "ensure_constraints", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "merge_notice_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(ingestor_mod, "upsert_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(ingestor_mod, "publish", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "ack", AsyncMock())
    monkeypatch.setattr(
        ingestor_mod, "get_settings", lambda: IngestorSettings(ingestor_reclaim_interval_seconds=0)
    )
    reclaimed = asyncio.Event()

    async def fake_autoclaim(*args, **kwargs):
        reclaimed.set()
        return []

    monkeypatch.setattr(ingestor_mod, "autoclaim_stale", fake_autoclaim)

    async def busy_read_group(*args, **kwargs):
        await asyncio.sleep(0.005)
        return [(STREAM, [entry])]

    monkeypatch.setattr(ingestor_mod, "read_group", busy_read_group)

    async def fake_serve_health(port, snapshot, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(ingestor_mod, "serve_health", fake_serve_health)

    task = asyncio.create_task(ingestor_mod.run_ingestor())
    try:
        await asyncio.wait_for(reclaimed.wait(), timeout=10)
    finally:
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError, SystemExit):
            pass


class _Driver(_FakeNeo4jDriver):
    async def close(self):
        pass


# --- P13: maintenance metrics + safe trimming ----------------------------------


async def test_maintenance_reports_lag_pending_dead_letter_and_trims(ctx):
    entries = await _deliver(ctx, "A", "B", "C")
    # Ack the first two so they are trimmable; leave the third pending.
    await ctx.redis.xack(STREAM, GROUP, entries[0][0], entries[1][0])
    await xadd_many(ctx.redis, "vestnik", [_payload("D")])  # unread
    await ctx.redis.xadd(DEAD_LETTER_STREAM, {"x": "1"})

    await run_maintenance(ctx)

    assert ctx.metrics["stream_pending"][STREAM] == 1
    assert ctx.metrics["stream_lag"][STREAM] >= 0
    assert ctx.metrics["dead_letter_length"] == 1
    remaining = [eid for eid, _ in await ctx.redis.xrange(STREAM)]
    assert entries[2][0] in remaining, "pending entry must survive trimming"
    assert len(remaining) >= 2, "unread entry must survive trimming"
