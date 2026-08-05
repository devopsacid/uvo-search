# Phase 2 — Ingestion Correctness & Throughput Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate silent data loss in the Redis Streams ingestion path, make failures visible instead of rendering as empty results, and remove the two quadratic/serialized hotspots that make backfill unsafe.

**Architecture:** The worker fleet (`uvo_workers`) is the live ingestion path. Five defects make it lossy or slow: consumer groups are created at the stream tail so pre-start entries are never delivered; consumer names are per-process UUIDs with no `XAUTOCLAIM`, so every restart strands its in-flight batch; `ensure_indexes()` is only reachable from the legacy orchestrator, so a worker-only deployment has no unique index; `upsert_batch` is per-document despite its name; and dedup runs an unindexed O(n²) scan on a 5-second debounce. Each is fixed independently, test-first.

**Tech Stack:** Python 3.12, redis-py asyncio, Motor (async PyMongo), Neo4j async driver, pytest-asyncio.

## Global Constraints

- Python 3.12+; all commands through `uv run`.
- **Prerequisite:** Phase 0 complete (green suite). Phase 1 is independent and may run in either order.
- Tests here are unit tests with mocked Redis/Mongo. Do **not** require a live Redis or Mongo for `tests/workers/` or `tests/pipeline/` — that is what `tests/e2e/` is for.
- Every task ends with `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q` green.
- Use `datetime.now(UTC)`, never the deprecated `datetime.utcnow()`. Import as `from datetime import UTC, datetime`.
- Conventional Commits.

---

### Task 1: Make health endpoints report actual health

**Files:**
- Modify: `src/uvo_workers/health.py`
- Test: `tests/workers/test_health_server.py` (create)

**Interfaces:**
- Produces: `serve_health(port: int, snapshot: Callable[[], dict], *, is_ready: Callable[[dict], bool] | None = None) -> None` — the third parameter is new and keyword-only, so existing two-argument call sites in `runner.py` and `ingestor.py` keep working unchanged.
- Produces: `default_is_ready(metrics: dict) -> bool` — the readiness rule used when no custom predicate is supplied. Phase 3's probe manifests depend on `/readyz` returning 503 when this is False.

`serve_health` currently ignores the request path and returns 200 unconditionally (`health.py:19-23`), so all 12 Kubernetes probe blocks can only detect a dead process, never a wedged or Redis-disconnected one.

- [ ] **Step 1: Write the failing test**

Create `tests/workers/test_health_server.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/workers/test_health_server.py -v`
Expected: FAIL with `ImportError: cannot import name 'default_is_ready'`.

- [ ] **Step 3: Write the implementation**

Replace the body of `src/uvo_workers/health.py`:

```python
"""Tiny asyncio-based HTTP server for /health, /healthz and /readyz."""

import asyncio
import json
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_READY_PATHS = frozenset({"/readyz", "/ready"})


def default_is_ready(metrics: dict) -> bool:
    """Readiness rule: connected to Redis and no error on the last cycle.

    Liveness deliberately stays unconditional — a dependency blip must not
    cause Kubernetes to restart the pod, which would turn a transient Redis
    outage into a cluster-wide restart storm.
    """
    if not metrics.get("redis_connected", False):
        return False
    return metrics.get("last_error") is None


async def serve_health(
    port: int,
    snapshot: Callable[[], dict],
    *,
    is_ready: Callable[[dict], bool] | None = None,
) -> None:
    ready_check = is_ready or default_is_ready

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await reader.readline()
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break

            parts = request_line.decode("latin-1").split()
            path = parts[1] if len(parts) > 1 else "/"

            metrics = snapshot()
            if path in _READY_PATHS and not ready_check(metrics):
                status = b"HTTP/1.1 503 Service Unavailable\r\n"
            else:
                status = b"HTTP/1.1 200 OK\r\n"

            body = json.dumps(metrics, default=str).encode()
            writer.write(status)
            writer.write(b"Content-Type: application/json\r\n")
            writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode())
            writer.write(body)
            await writer.drain()
        except Exception as exc:
            logger.debug("health handler error: %s", exc)
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    async with server:
        await server.serve_forever()
```

`/health` keeps its existing always-200 behaviour so nothing that polls it breaks; only the new `/readyz` path gates on readiness.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/workers/test_health_server.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed.

```bash
git add src/uvo_workers/health.py tests/workers/test_health_server.py
git commit -m "feat(workers): add /readyz returning 503 when Redis is down or last cycle errored"
```

---

### Task 2: Create consumer groups from the stream head

**Files:**
- Modify: `src/uvo_pipeline/streams.py:30-35`
- Test: `tests/pipeline/test_streams_consumer_group.py` (create)

`xgroup_create(..., id="$")` creates the group at the **tail**. Any entry an extractor XADDs before the ingestor first starts is never delivered to the group — silent cold-start data loss on a fresh Redis or when extractors deploy ahead of the ingestor.

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_streams_consumer_group.py`:

```python
"""Consumer groups must start at the stream head, not the tail."""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ResponseError

from uvo_pipeline.streams import ensure_consumer_group


@pytest.mark.asyncio
async def test_group_created_from_stream_head():
    """id='0' replays entries already in the stream; id='$' would skip them."""
    redis = AsyncMock()
    await ensure_consumer_group(redis, "notices:crz", "ingestor")
    redis.xgroup_create.assert_awaited_once_with(
        "notices:crz", "ingestor", id="0", mkstream=True
    )


@pytest.mark.asyncio
async def test_existing_group_is_tolerated():
    redis = AsyncMock()
    redis.xgroup_create.side_effect = ResponseError("BUSYGROUP Consumer Group name already exists")
    await ensure_consumer_group(redis, "notices:crz", "ingestor")


@pytest.mark.asyncio
async def test_other_response_errors_propagate():
    redis = AsyncMock()
    redis.xgroup_create.side_effect = ResponseError("WRONGTYPE")
    with pytest.raises(ResponseError):
        await ensure_consumer_group(redis, "notices:crz", "ingestor")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/pipeline/test_streams_consumer_group.py -v`
Expected: FAIL on the first test — called with `id="$"`.

- [ ] **Step 3: Change the group start position**

In `src/uvo_pipeline/streams.py`, change the `ensure_consumer_group` body:

```python
async def ensure_consumer_group(redis: aioredis.Redis, stream: str, group: str) -> None:
    """Create the consumer group at the stream head.

    id="0" replays every entry currently in the stream. id="$" (the previous
    value) starts at the tail, so entries XADDed before the consumer first
    started are never delivered — silent data loss whenever the ingestor is
    deployed after the extractors or Redis is recreated.
    """
    try:
        await redis.xgroup_create(stream, group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/pipeline/test_streams_consumer_group.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed.

```bash
git add src/uvo_pipeline/streams.py tests/pipeline/test_streams_consumer_group.py
git commit -m "fix(pipeline): create consumer groups at stream head to stop cold-start data loss"
```

---

### Task 3: Reclaim orphaned entries with a stable consumer name

**Files:**
- Modify: `src/uvo_pipeline/streams.py` (add `autoclaim_stale`)
- Modify: `src/uvo_workers/ingestor.py:76,151`
- Test: `tests/pipeline/test_streams_autoclaim.py` (create)

**Interfaces:**
- Produces: `autoclaim_stale(redis, stream, group, consumer, *, min_idle_ms=60_000, count=100) -> list[tuple[bytes, dict]]` — returns entries reclaimed from dead consumers, in the same `(entry_id, fields)` shape `read_group` yields, so the ingestor's existing decode loop handles both identically.

The consumer name is `uuid.uuid4().hex`, fresh on every process start (`ingestor.py:76`). Entries delivered but not acked stay in the Pending Entries List under a consumer name that never returns, and nothing ever calls `XAUTOCLAIM`. Every pod restart permanently strands its in-flight batch and grows the PEL — this is also what blocks running more than one ingestor replica.

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_streams_autoclaim.py`:

```python
"""Orphaned pending entries must be reclaimable after a consumer dies."""

from unittest.mock import AsyncMock

import pytest

from uvo_pipeline.streams import autoclaim_stale


@pytest.mark.asyncio
async def test_autoclaim_returns_reclaimed_entries():
    redis = AsyncMock()
    # redis-py returns (next_cursor, entries, deleted_ids)
    redis.xautoclaim.return_value = (
        b"0-0",
        [(b"1700000000000-0", {b"payload": b"{}", b"hash": b"h", b"run": b"r"})],
        [],
    )
    entries = await autoclaim_stale(redis, "notices:crz", "ingestor", "ingestor-0")
    assert len(entries) == 1
    assert entries[0][0] == b"1700000000000-0"


@pytest.mark.asyncio
async def test_autoclaim_passes_min_idle_time():
    redis = AsyncMock()
    redis.xautoclaim.return_value = (b"0-0", [], [])
    await autoclaim_stale(redis, "notices:crz", "ingestor", "ingestor-0", min_idle_ms=30_000)
    kwargs = redis.xautoclaim.await_args.kwargs
    assert kwargs["min_idle_time"] == 30_000


@pytest.mark.asyncio
async def test_autoclaim_returns_empty_on_error():
    """A reclaim failure must not take down the ingest loop."""
    redis = AsyncMock()
    redis.xautoclaim.side_effect = RuntimeError("NOGROUP")
    assert await autoclaim_stale(redis, "notices:crz", "ingestor", "ingestor-0") == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/pipeline/test_streams_autoclaim.py -v`
Expected: FAIL with `ImportError: cannot import name 'autoclaim_stale'`.

- [ ] **Step 3: Write the implementation**

Append to `src/uvo_pipeline/streams.py`:

```python
async def autoclaim_stale(
    redis: aioredis.Redis,
    stream: str,
    group: str,
    consumer: str,
    *,
    min_idle_ms: int = 60_000,
    count: int = 100,
) -> list[tuple[bytes, dict]]:
    """Reclaim entries pending longer than min_idle_ms from dead consumers.

    Consumer names are per-pod. When a pod dies mid-batch its delivered but
    unacked entries stay in the PEL under a name that never returns, so
    without this they are stranded permanently and the PEL grows without
    bound. Returns entries in the same shape read_group yields.

    Failures are swallowed and reported as "nothing reclaimed": a reclaim
    problem must never stop the main ingest loop from making progress.
    """
    try:
        _cursor, entries, _deleted = await redis.xautoclaim(
            name=stream,
            groupname=group,
            consumername=consumer,
            min_idle_time=min_idle_ms,
            start_id="0-0",
            count=count,
        )
    except Exception as exc:
        logger.warning("xautoclaim failed on %s: %s", stream, exc)
        return []
    return list(entries or [])
```

Add the logger to the top of `streams.py` if absent:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/pipeline/test_streams_autoclaim.py -v`
Expected: 3 passed.

- [ ] **Step 5: Give the ingestor a stable consumer name**

In `src/uvo_workers/ingestor.py`, the consumer identity must survive restarts so its own PEL entries are re-delivered. Kubernetes sets `HOSTNAME` to the pod name, which is stable for a StatefulSet and stable-enough for a Deployment pod across in-place restarts. Add the import and change the identity block at line 76:

```python
import os
```

```python
    instance_id = uuid.uuid4().hex
    # Consumer name must be stable across restarts so this pod's own pending
    # entries are redelivered to it. instance_id stays random for log
    # correlation of a single process lifetime.
    consumer_name = os.environ.get("HOSTNAME") or f"ingestor-{instance_id[:8]}"
```

Then replace `instance_id` with `consumer_name` in the `read_group` call at line 151 only:

```python
                results = await read_group(
                    redis_client,
                    "ingestor",
                    consumer_name,
                    _STREAMS,
                    count=settings.ingestor_batch_size,
                    block_ms=5000,
                )
```

Leave every `log_event(..., instance_id=instance_id)` call unchanged.

- [ ] **Step 6: Reclaim stale entries each loop iteration**

Add the import in `ingestor.py`:

```python
from uvo_pipeline.streams import ack, autoclaim_stale, decode_entry, ensure_consumer_group, read_group
```

Then inside the `while not stop_event.is_set():` loop, immediately after the `if not results: continue` guard is evaluated — replace that guard with a reclaim pass so an idle loop still drains the PEL:

```python
            if not results:
                reclaimed = []
                for stream in _STREAMS:
                    entries = await autoclaim_stale(
                        redis_client, stream, "ingestor", consumer_name
                    )
                    if entries:
                        reclaimed.append((stream, entries))
                        logger.info(
                            "ingestor: reclaimed %d stale entries from %s", len(entries), stream
                        )
                if not reclaimed:
                    continue
                results = reclaimed
```

Because `autoclaim_stale` returns the same `(entry_id, fields)` shape, the existing `for stream_name, entries in results:` body below handles reclaimed entries with no further change.

- [ ] **Step 7: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed.

```bash
git add src/uvo_pipeline/streams.py src/uvo_workers/ingestor.py tests/pipeline/test_streams_autoclaim.py
git commit -m "fix(workers): stable consumer name + XAUTOCLAIM so restarts no longer strand entries"
```

---

### Task 4: Ensure indexes exist in a worker-only deployment

**Files:**
- Modify: `src/uvo_workers/ingestor.py` (call `ensure_indexes` / `ensure_constraints` at startup)
- Test: `tests/workers/test_ingestor_startup_indexes.py` (create)

`ensure_indexes()` (`loaders/mongo.py:38`) is called only from `orchestrator.py:112` — the legacy path. The kustomize base deliberately excludes the pipeline Job, so a worker-only deployment runs with **no unique index on `(source, source_id)`**, no TTL on `ingestion_log`, and no Neo4j constraints. The registry lookup at `mongo.py:196` degrades to a collection scan per batch and the idempotency guarantee is unenforced.

- [ ] **Step 1: Write the failing test**

Create `tests/workers/test_ingestor_startup_indexes.py`:

```python
"""The ingestor must provision indexes itself — it is the only writer in a
worker-only deployment, where the legacy orchestrator never runs."""

import inspect

from uvo_workers import ingestor


def test_ingestor_calls_ensure_indexes():
    source = inspect.getsource(ingestor.run_ingestor)
    assert "ensure_indexes" in source, (
        "run_ingestor must call ensure_indexes at startup; the pipeline Job that "
        "used to do it is excluded from the kustomize base"
    )


def test_ingestor_calls_ensure_constraints():
    source = inspect.getsource(ingestor.run_ingestor)
    assert "ensure_constraints" in source, (
        "run_ingestor must call ensure_constraints — MERGE is only atomic when "
        "backed by a uniqueness constraint"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/workers/test_ingestor_startup_indexes.py -v`
Expected: FAIL — neither name appears in `run_ingestor`.

- [ ] **Step 3: Confirm the constraint helper's name and signature**

Run: `grep -n "^async def ensure_constraints" src/uvo_pipeline/loaders/neo4j.py`
Expected: shows `async def ensure_constraints(session)` or similar. Note whether it takes a session or a driver — the call in Step 4 must match.

- [ ] **Step 4: Call both at ingestor startup**

In `src/uvo_workers/ingestor.py`, add the imports:

```python
from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch
from uvo_pipeline.loaders.neo4j import ensure_constraints, merge_notice_batch
```

Then, immediately after the `neo4j_driver = AsyncGraphDatabase.driver(...)` block and before the `try:` that opens the main loop, add:

```python
    # The ingestor is the only writer in a worker-only deployment; the legacy
    # pipeline Job that used to provision these is excluded from the kustomize
    # base. Both helpers are idempotent, so running them on every start is safe.
    try:
        await ensure_indexes(db)
        async with neo4j_driver.session() as bootstrap_session:
            await ensure_constraints(bootstrap_session)
        logger.info("ingestor: indexes and constraints ensured")
    except Exception as exc:
        logger.error("ingestor: failed to ensure indexes/constraints: %s", exc, exc_info=True)
        await log_event(
            db,
            level="error",
            event="index_bootstrap_failed",
            component="ingestor",
            instance_id=instance_id,
            message=redact_exception(exc),
        )
```

Adjust the `ensure_constraints` call to match the signature confirmed in Step 3. Import `redact_exception` from `uvo_workers.errors` if Phase 1 Task 4 is already merged; otherwise use `f"{type(exc).__name__}"`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/workers/test_ingestor_startup_indexes.py -v`
Expected: 2 passed.

- [ ] **Step 6: Add the missing dedup indexes**

Dedup filters on fields with no index at all, which is why it collection-scans. In `src/uvo_pipeline/loaders/mongo.py`, inside `ensure_indexes`, add after the existing `notices` index block:

```python
    # Indexes backing cross-source dedup. Without these, dedup collection-scans
    # `notices` on every trigger.
    await _ensure_index(db.notices, [("ingested_at", -1)], name="ingested_at_desc")
    await _ensure_index(db.notices, [("pipeline_run_id", 1)], name="pipeline_run_id")
    await _ensure_index(db.notices, [("title_slug", 1)], name="title_slug")
```

- [ ] **Step 7: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed.

```bash
git add src/uvo_workers/ingestor.py src/uvo_pipeline/loaders/mongo.py tests/workers/test_ingestor_startup_indexes.py
git commit -m "fix(workers): provision Mongo indexes and Neo4j constraints at ingestor startup"
```

---

### Task 5: Make `upsert_batch` actually bulk

**Files:**
- Modify: `src/uvo_pipeline/loaders/mongo.py:165-283`
- Test: `tests/pipeline/test_upsert_batch_bulk.py` (create)

The docstring says "Bulk upsert" but the implementation issues per-document awaits in a Python loop — roughly 1500–2000 serialized round-trips for a 500-notice batch. The unchanged path also costs a write per notice, so re-running N unchanged notices is N writes rather than zero.

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_upsert_batch_bulk.py`:

```python
"""upsert_batch must issue bulk operations, not per-document awaits."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_pipeline.loaders.mongo import upsert_batch
from uvo_pipeline.models import CanonicalNotice


def _notice(source_id: str) -> CanonicalNotice:
    return CanonicalNotice(
        source="crz",
        source_id=source_id,
        title=f"Notice {source_id}",
        pipeline_run_id="run-1",
    )


def _db_with_no_existing_registry() -> MagicMock:
    db = MagicMock()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    db.ingested_docs.find.return_value = cursor
    db.notices.bulk_write = AsyncMock(return_value=MagicMock(upserted_count=3, modified_count=0))
    db.ingested_docs.bulk_write = AsyncMock(return_value=MagicMock())
    db.procurers.bulk_write = AsyncMock(return_value=MagicMock())
    db.suppliers.bulk_write = AsyncMock(return_value=MagicMock())
    return db


@pytest.mark.asyncio
async def test_uses_bulk_write_not_per_document_updates():
    db = _db_with_no_existing_registry()
    await upsert_batch(db, [_notice("a"), _notice("b"), _notice("c")])
    db.notices.bulk_write.assert_awaited()
    db.notices.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_one_bulk_call_per_collection_per_batch():
    db = _db_with_no_existing_registry()
    await upsert_batch(db, [_notice("a"), _notice("b"), _notice("c")])
    assert db.notices.bulk_write.await_count == 1
    assert db.ingested_docs.bulk_write.await_count == 1


@pytest.mark.asyncio
async def test_empty_batch_issues_no_writes():
    db = _db_with_no_existing_registry()
    result = await upsert_batch(db, [])
    db.notices.bulk_write.assert_not_awaited()
    assert result["inserted"] == 0
```

If `CanonicalNotice` requires fields beyond those in `_notice`, run `uv run python -c "from uvo_pipeline.models import CanonicalNotice; print(CanonicalNotice.model_fields.keys())"` and add the required ones.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/pipeline/test_upsert_batch_bulk.py -v`
Expected: FAIL — `bulk_write` never awaited; `update_one` called instead.

- [ ] **Step 3: Rewrite the write phase using bulk_write**

In `src/uvo_pipeline/loaders/mongo.py`, add the import:

```python
from pymongo import UpdateOne
```

Replace the `for notice in batch:` write loop (the block spanning the `reg_entry is None` / `content_hash` equal / else branches) with operation accumulation followed by two bulk calls:

```python
        notice_ops: list[UpdateOne] = []
        registry_ops: list[UpdateOne] = []

        for notice in batch:
            key = (notice.source, notice.source_id)
            reg_entry = registry.get(key)
            filt = {"source": notice.source, "source_id": notice.source_id}

            if reg_entry is not None and reg_entry["content_hash"] == notice.content_hash:
                # Unchanged: touch the registry only, never rewrite the notice.
                registry_ops.append(
                    UpdateOne(filt, {"$set": {"last_seen_at": now}, "$inc": {"skipped_count": 1}})
                )
                skipped += 1
                continue

            doc = notice.model_dump(mode="json")
            notice_ops.append(
                UpdateOne(
                    filt,
                    {
                        "$set": {k: v for k, v in doc.items() if k != "ingested_at"},
                        "$setOnInsert": {"ingested_at": doc["ingested_at"]},
                    },
                    upsert=True,
                )
            )
            registry_ops.append(
                UpdateOne(
                    filt,
                    {
                        "$set": {
                            "content_hash": notice.content_hash,
                            "last_seen_at": now,
                            "pipeline_run_id": notice.pipeline_run_id,
                        },
                        "$setOnInsert": {"ingested_at": now, "skipped_count": 0},
                    },
                    upsert=True,
                )
            )

        if notice_ops:
            try:
                result = await db.notices.bulk_write(notice_ops, ordered=False)
                inserted += result.upserted_count
                updated += result.modified_count
            except Exception as exc:
                logger.error("Bulk notice upsert failed: %s", exc)
                errors += len(notice_ops)

        if registry_ops:
            try:
                await db.ingested_docs.bulk_write(registry_ops, ordered=False)
            except Exception as exc:
                logger.error("Bulk registry upsert failed: %s", exc)
                errors += len(registry_ops)
```

`ordered=False` lets independent documents proceed when one fails, instead of aborting the batch at the first error.

- [ ] **Step 4: Correct the docstring**

Change the `upsert_batch` docstring's first line so it matches reality:

```python
    """Bulk upsert notices via bulk_write, skipping unchanged docs via the
    ingested_docs registry.

    Returns {inserted, updated, skipped, errors}.
    """
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/pipeline/test_upsert_batch_bulk.py -v`
Expected: 3 passed.

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed. Existing `tests/pipeline/` tests that assert on `update_one` calls must be updated to assert on `bulk_write` — the behaviour they were pinning is what changed.

```bash
git add src/uvo_pipeline/loaders/mongo.py tests/pipeline/test_upsert_batch_bulk.py
git commit -m "perf(pipeline): replace per-document upserts with bulk_write in upsert_batch"
```

---

### Task 6: Rate-limit dedup and stop re-scanning settled groups

**Files:**
- Modify: `src/uvo_workers/dedup.py` (debounce → minimum interval)
- Modify: `src/uvo_pipeline/dedup.py` (Pass 1 filter + projection)
- Test: `tests/workers/test_dedup_rate_limit.py` (create)

The dedup worker triggers 5 seconds after **any** `notices:written` message, and the ingestor publishes one per batch. During backfill this re-runs a full O(n²) scan every ~5 seconds. Pass 1 also omits the `canonical_id: None` filter that Pass 2 has, so it reprocesses already-settled groups.

- [ ] **Step 1: Read the current trigger logic before changing it**

Run: `sed -n '1,60p' src/uvo_workers/dedup.py && grep -n "canonical_id\|to_list\|find(" src/uvo_pipeline/dedup.py`
Expected: shows the 5-second debounce constant in the worker, and in the library the Pass 1 `find(...)` without a `canonical_id` filter plus the `to_list(length=None)` full load. Record the exact constant name and the Pass 1 filter dict — the edits below must match what is actually there.

- [ ] **Step 2: Write the failing test**

Create `tests/workers/test_dedup_rate_limit.py`:

```python
"""Dedup must not re-run on every batch — it is an O(n^2) scan."""

from uvo_workers import dedup


def test_minimum_interval_is_at_least_60_seconds():
    assert dedup.MIN_DEDUP_INTERVAL_SECONDS >= 60, (
        "dedup performs a full-collection quadratic scan; running it every few "
        "seconds during backfill saturates MongoDB"
    )


def test_should_run_blocks_within_interval():
    assert dedup.should_run(last_run_monotonic=1000.0, now_monotonic=1000.0 + 5) is False


def test_should_run_allows_after_interval():
    later = 1000.0 + dedup.MIN_DEDUP_INTERVAL_SECONDS + 1
    assert dedup.should_run(last_run_monotonic=1000.0, now_monotonic=later) is True


def test_should_run_allows_first_ever_run():
    assert dedup.should_run(last_run_monotonic=None, now_monotonic=1000.0) is True
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/workers/test_dedup_rate_limit.py -v`
Expected: FAIL with `AttributeError: module 'uvo_workers.dedup' has no attribute 'MIN_DEDUP_INTERVAL_SECONDS'`.

- [ ] **Step 4: Add the rate-limit gate**

In `src/uvo_workers/dedup.py`, add at module level:

```python
# Dedup performs a quadratic scan over a 30-day window. The ingestor publishes
# notices:written once per batch, so a short debounce means a full re-scan every
# few seconds during backfill. This is a floor on how often the scan may start,
# independent of how many write notifications arrive.
MIN_DEDUP_INTERVAL_SECONDS = 300.0


def should_run(last_run_monotonic: float | None, now_monotonic: float) -> bool:
    """True when enough time has passed since the last dedup pass."""
    if last_run_monotonic is None:
        return True
    return (now_monotonic - last_run_monotonic) >= MIN_DEDUP_INTERVAL_SECONDS
```

Then, in the worker's trigger loop, gate the dedup invocation on it. Track the last run with `time.monotonic()` (never wall-clock — it must not jump when NTP corrects the clock):

```python
import time
```

```python
    last_dedup_run: float | None = None
```

and immediately before the call that runs the dedup pass:

```python
            now = time.monotonic()
            if not should_run(last_dedup_run, now):
                logger.debug("dedup: within minimum interval, skipping trigger")
                continue
            last_dedup_run = now
```

Keep the existing debounce that coalesces bursts — this gate sits on top of it as a floor.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/workers/test_dedup_rate_limit.py -v`
Expected: 4 passed.

- [ ] **Step 6: Skip settled groups and stop loading full documents in Pass 1**

In `src/uvo_pipeline/dedup.py`, apply two changes to Pass 1, using the exact filter dict recorded in Step 1:

Add the same already-settled guard Pass 2 uses, so notices that already have a canonical id are not reprocessed:

```python
    # Skip notices already assigned to a canonical group. Without this, Pass 1
    # reprocesses settled groups on every run and the reported match count is a
    # re-count rather than new matches.
    query["canonical_id"] = None
```

And project only the fields the scan reads, instead of loading whole documents:

```python
    _DEDUP_PROJECTION = {
        "source": 1,
        "source_id": 1,
        "title_slug": 1,
        "publication_date": 1,
        "cpv_code": 1,
        "canonical_id": 1,
        "procurer.ico": 1,
    }
```

```python
    docs = await db.notices.find(query, _DEDUP_PROJECTION).to_list(length=None)
```

If the scan reads a field not in the projection, add it — run the pipeline tests to find out rather than guessing.

- [ ] **Step 7: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed.

```bash
git add src/uvo_workers/dedup.py src/uvo_pipeline/dedup.py tests/workers/test_dedup_rate_limit.py
git commit -m "perf(dedup): enforce a 5-minute minimum interval, skip settled groups, project fields"
```

---

### Task 7: Make backend failures visible instead of empty

**Files:**
- Create: `src/uvo_api/errors.py`
- Modify: `src/uvo_api/app.py` (register handler)
- Modify: `src/uvo_api/routers/suppliers.py`, `procurers.py`, `search.py`, `dashboard.py`, `contracts.py`
- Test: `tests/api/test_error_propagation.py` (create)

`McpToolError` is raised at three sites in `mcp_client.py` and caught nowhere. Worse, routers call `result.get("items", [])` without checking for an `error` key, so an MCP `{"error": "MongoDB not configured", "status_code": 503}` envelope yields `[]` and **HTTP 200**. A total database outage looks like an empty search and alerts nothing.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_error_propagation.py`:

```python
"""A backend outage must surface as 5xx, never as an empty 200."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app
from uvo_api.mcp_client import McpToolError

ERROR_ENVELOPE = {"error": "MongoDB not configured", "status_code": 503}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    monkeypatch.setenv("API_MONGODB_URI", "mongodb://test:test@localhost:27017")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_error_envelope_is_not_an_empty_200(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(return_value=ERROR_ENVELOPE)):
        response = client.get("/api/suppliers")
    assert response.status_code == 503


def test_mcp_tool_error_becomes_503(client):
    with patch(
        "uvo_api.routers.suppliers.call_tool",
        new=AsyncMock(side_effect=McpToolError("connection refused")),
    ):
        response = client.get("/api/suppliers")
    assert response.status_code == 503


def test_error_detail_does_not_leak_internals(client):
    with patch(
        "uvo_api.routers.suppliers.call_tool",
        new=AsyncMock(side_effect=McpToolError("mongodb://uvo:s3cret@mongo:27017 refused")),
    ):
        response = client.get("/api/suppliers")
    assert "s3cret" not in response.text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/api/test_error_propagation.py -v`
Expected: FAIL — the first returns 200 with an empty list; the second returns 500 with a leaked message.

- [ ] **Step 3: Write the shared helper and handler**

Create `src/uvo_api/errors.py`:

```python
"""Uniform error handling for MCP-backed routes."""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from uvo_api.mcp_client import McpToolError

logger = logging.getLogger(__name__)


def raise_for_tool_error(result: dict, tool_name: str) -> dict:
    """Convert an MCP error envelope into an HTTP error.

    MCP tools signal backend unavailability with {"error": ..., "status_code": ...}
    rather than raising. Routers that call result.get("items", []) on such a
    payload silently return an empty 200, so a total database outage is
    indistinguishable from "no results" and nothing alerts.
    """
    if isinstance(result, dict) and result.get("error"):
        status_code = int(result.get("status_code", 503))
        logger.error("MCP tool %s returned error envelope: %s", tool_name, result["error"])
        raise HTTPException(status_code=status_code, detail="Backend temporarily unavailable")
    return result


def register_error_handlers(app: FastAPI) -> None:
    """Map McpToolError to 503 without leaking the underlying message."""

    @app.exception_handler(McpToolError)
    async def _handle_mcp_tool_error(request: Request, exc: McpToolError) -> JSONResponse:
        # Full detail to stderr only — driver messages embed connection URIs
        # with credentials.
        logger.error("MCP call failed for %s: %s", request.url.path, exc, exc_info=True)
        return JSONResponse(
            status_code=503,
            content={"detail": "Backend temporarily unavailable"},
        )
```

- [ ] **Step 4: Register the handler**

In `src/uvo_api/app.py`, add the import and call it inside `create_app` after the middleware block:

```python
from uvo_api.errors import register_error_handlers
```

```python
    register_error_handlers(app)
```

- [ ] **Step 5: Guard every list-envelope read**

In each of `suppliers.py`, `procurers.py`, `search.py`, `dashboard.py`, and `contracts.py`, add the import:

```python
from uvo_api.errors import raise_for_tool_error
```

Then wrap each `call_tool` result before reading `items`. Find them with `grep -n 'call_tool\|\.get("items"' src/uvo_api/routers/suppliers.py` and change each pair from:

```python
    result = await call_tool("find_supplier", args)
    items = result.get("items", [])
```

to:

```python
    result = raise_for_tool_error(await call_tool("find_supplier", args), "find_supplier")
    items = result.get("items", [])
```

`contracts.py` already honours the tool's `status_code` at its own call site — replace that bespoke branch with `raise_for_tool_error` so all five routers behave identically.

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/api/test_error_propagation.py -v`
Expected: 3 passed.

- [ ] **Step 7: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed.

```bash
git add src/uvo_api/errors.py src/uvo_api/app.py src/uvo_api/routers/ tests/api/test_error_propagation.py
git commit -m "fix(api): surface backend outages as 503 instead of empty 200 responses"
```

---

### Task 8: Fix contract value filtering and totals

**Files:**
- Modify: `src/uvo_mcp/tools/procurements.py` (accept value bounds)
- Modify: `src/uvo_api/routers/contracts.py:50-55`
- Test: `tests/api/test_contract_value_filter.py` (create)

`contracts.py:50-55` filters `value_min`/`value_max` in Python **after** pagination and then overwrites `total` with the post-filter page count. Page counts are wrong and results are silently incomplete.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_contract_value_filter.py`:

```python
"""Value filtering must happen in the query, not after pagination."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

RESPONSE = {"items": [], "total": 0}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    monkeypatch.setenv("API_MONGODB_URI", "mongodb://test:test@localhost:27017")
    return TestClient(create_app())


def test_value_bounds_are_pushed_to_the_tool(client):
    mock = AsyncMock(return_value=RESPONSE)
    with patch("uvo_api.routers.contracts.call_tool", new=mock):
        client.get("/api/contracts", params={"value_min": 1000, "value_max": 5000})
    args = mock.await_args.args[1]
    assert args["value_min"] == 1000
    assert args["value_max"] == 5000


def test_total_comes_from_the_tool_not_the_page(client):
    """total must reflect the full filtered result set, not the current page."""
    mock = AsyncMock(return_value={"items": [], "total": 4321})
    with patch("uvo_api.routers.contracts.call_tool", new=mock):
        response = client.get("/api/contracts", params={"value_min": 1000})
    assert response.json()["total"] == 4321
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/api/test_contract_value_filter.py -v`
Expected: FAIL — the bounds are not forwarded, and `total` is overwritten with the page length.

- [ ] **Step 3: Accept the bounds in the MCP tool**

In `src/uvo_mcp/tools/procurements.py`, add two optional parameters to the `search_completed_procurements` signature:

```python
    value_min: float | None = None,
    value_max: float | None = None,
```

and translate them into the Mongo match stage alongside the existing filters:

```python
    if value_min is not None or value_max is not None:
        bounds: dict[str, float] = {}
        if value_min is not None:
            bounds["$gte"] = value_min
        if value_max is not None:
            bounds["$lte"] = value_max
        match_stage["contract_value"] = bounds
```

Use the actual value field name from the notice schema — confirm with `grep -n "contract_value\|hodnota" src/uvo_pipeline/models.py` and substitute the real name. Add the filter to the same dict the other filters use; find it with `grep -n "match_stage\|\$match" src/uvo_mcp/tools/procurements.py`.

- [ ] **Step 4: Forward the bounds and stop overwriting total**

In `src/uvo_api/routers/contracts.py`, delete the post-pagination Python filter at lines 50-55 and the `total` reassignment, then add the bounds to the args dict built for the tool call:

```python
    if value_min is not None:
        args["value_min"] = value_min
    if value_max is not None:
        args["value_max"] = value_max
```

The response now returns `result["total"]` from the tool unchanged.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/api/test_contract_value_filter.py -v`
Expected: 2 passed.

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed.

```bash
git add src/uvo_mcp/tools/procurements.py src/uvo_api/routers/contracts.py tests/api/test_contract_value_filter.py
git commit -m "fix(api): push contract value bounds into the query and report the true total"
```

---

## Done when

- `/readyz` returns 503 when Redis is disconnected or the last cycle errored; `/healthz` stays 200.
- Consumer groups are created with `id="0"`; a stream populated before the ingestor starts is fully consumed.
- The ingestor uses a `HOSTNAME`-derived consumer name and reclaims entries idle >60s via `XAUTOCLAIM`.
- `ensure_indexes` and `ensure_constraints` run at ingestor startup; `notices` has indexes on `ingested_at`, `pipeline_run_id`, and `title_slug`.
- `upsert_batch` issues one `bulk_write` per collection per batch; unchanged notices cost no notice write.
- Dedup cannot start more than once per 5 minutes and skips notices that already have a `canonical_id`.
- An MCP error envelope or `McpToolError` produces 503 with no credential leakage, never an empty 200.
- Contract value bounds are applied in the query and `total` reflects the full filtered set.
- Full suite green.

## Deliberately out of scope

- **Retiring the legacy `uvo_pipeline` orchestrator write path** (architecture finding #2). It is a large, independent change that deletes the duplicate-write class entirely — it deserves its own plan once the worker path above is proven correct.
- **Metrics/structured logging** and **moving the MCP cache to Redis** — prerequisites for HPA, covered in Phase 3.
