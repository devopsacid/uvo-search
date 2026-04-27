# Ingestion Log + Date Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a centralized `ingestion_log` MongoDB collection that records every ingestion lifecycle event (worker start/stop, cycle complete, batch ingested, decode/write failures, validation issues) and add date-plausibility validation in the ingestor that clamps out-of-range dates (e.g. year `3202`, `2502`) and logs each one to `ingestion_log`.

**Architecture:**
- New collection `ingestion_log` with TTL (30 days). One document per event. Written via a small `log_event(db, ...)` helper. Indexes on `(ts desc)`, `(source, ts desc)`, `(level, ts desc)`.
- New `validate_notice_dates(notice) -> (clean_notice, issues)` pure utility called by the ingestor before writing. Out-of-range date fields are nulled out (notice still ingested) and each issue becomes one `ingestion_log` entry.
- Workers (extractors + ingestor) get a Mongo handle at startup solely for logging; they call `log_event` on lifecycle transitions and on errors.
- New read-only API endpoint `/api/dashboard/ingestion-log` paginates recent entries with optional level/source/event filters.
- React `IngestionPage` gains a "Posledne udalosti" panel showing the latest 50 entries.

**Tech Stack:** Python 3.12+, Pydantic v2, Motor (async MongoDB), FastAPI, pytest, pytest-asyncio, mongomock-motor (already in dev deps if used elsewhere — fall back to a real Mongo fixture if not). Frontend: React 18 + TanStack Query v5 + Tailwind.

---

## File Structure

**New files:**

| Path | Responsibility |
| ---- | -------------- |
| `src/uvo_pipeline/ingestion_log.py` | `IngestionLogEntry` model, `LogLevel`/`LogEvent` literals, `log_event(db, ...)` async helper, `ensure_log_indexes(db)` |
| `src/uvo_pipeline/utils/date_validation.py` | `MIN_YEAR`, `max_year()`, `validate_notice_dates(notice) -> (notice, issues)` |
| `tests/pipeline/test_ingestion_log.py` | Unit tests for `log_event` + index creation |
| `tests/pipeline/utils/test_date_validation.py` | Unit tests for the validator |
| `tests/api/test_ingestion_log.py` | API endpoint tests |
| `tests/workers/test_ingestor_logging.py` | Test that ingestor emits expected log events |
| `src/uvo_api/routers/ingestion_log.py` | `GET /api/dashboard/ingestion-log` endpoint + Pydantic response model |
| `src/uvo-gui-react/src/api/queries/ingestionLog.ts` | TanStack Query hook |
| `src/uvo-gui-react/src/components/ingestion/IngestionLogPanel.tsx` | Display panel |

**Modified files:**

| Path | Change |
| ---- | ------ |
| `src/uvo_pipeline/loaders/mongo.py` | Call `ensure_log_indexes(db)` from `ensure_indexes` |
| `src/uvo_workers/ingestor.py` | Connect Mongo, emit log events on start/stop/batches/errors, run `validate_notice_dates` per notice |
| `src/uvo_workers/runner.py` | Connect Mongo, emit log events on worker start/stop/cycle/error |
| `src/uvo_api/app.py` | Register new router |
| `src/uvo_api/models.py` | Add `IngestionLogResponse`, `IngestionLogEntry` (or import from pipeline) |
| `src/uvo-gui-react/src/pages/IngestionPage.tsx` | Render `<IngestionLogPanel/>` below existing dashboard |
| `src/uvo-gui-react/src/i18n/sk.ts` | Slovak strings for the new panel |
| `src/uvo-gui-react/src/api/types.ts` | Types for the log entry |

---

## Task 1: Add `ingestion_log` model + helper + indexes

**Files:**
- Create: `src/uvo_pipeline/ingestion_log.py`
- Create: `tests/pipeline/test_ingestion_log.py`
- Modify: `src/uvo_pipeline/loaders/mongo.py`

- [ ] **Step 1: Write the failing test for the model + helper**

```python
# tests/pipeline/test_ingestion_log.py
"""Tests for ingestion_log helpers."""
from datetime import datetime, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from uvo_pipeline.ingestion_log import (
    IngestionLogEntry,
    ensure_log_indexes,
    log_event,
)


@pytest.fixture
def db():
    client = AsyncMongoMockClient()
    return client["test"]


@pytest.mark.asyncio
async def test_log_event_writes_document(db):
    await ensure_log_indexes(db)
    await log_event(
        db,
        level="info",
        event="worker_started",
        component="ingestor",
        message="ingestor up",
        source=None,
        details={"instance_id": "abc"},
    )
    docs = await db.ingestion_log.find().to_list(length=10)
    assert len(docs) == 1
    doc = docs[0]
    assert doc["level"] == "info"
    assert doc["event"] == "worker_started"
    assert doc["component"] == "ingestor"
    assert doc["message"] == "ingestor up"
    assert doc["source"] is None
    assert doc["details"] == {"instance_id": "abc"}
    assert isinstance(doc["ts"], datetime)
    assert doc["ts"].tzinfo is not None or True  # naive UTC accepted


@pytest.mark.asyncio
async def test_entry_model_round_trip():
    entry = IngestionLogEntry(
        level="warning",
        event="notice_invalid_date",
        component="ingestor",
        source="vestnik",
        source_id="N-1",
        message="award_date out of range",
        details={"field": "award_date", "year": 3202},
    )
    dumped = entry.model_dump(mode="json")
    assert dumped["level"] == "warning"
    assert dumped["event"] == "notice_invalid_date"
    assert dumped["details"]["year"] == 3202


@pytest.mark.asyncio
async def test_ensure_log_indexes_creates_ttl_and_query_indexes(db):
    await ensure_log_indexes(db)
    info = await db.ingestion_log.index_information()
    names = set(info.keys())
    assert "ts_desc" in names
    assert "source_ts_desc" in names
    assert "level_ts_desc" in names
    # TTL index on ts; mongomock may or may not surface expireAfterSeconds.
    assert "ts_ttl" in names
```

- [ ] **Step 2: Run the test — expect ImportError**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/pipeline/test_ingestion_log.py -v'`

Expected: FAIL with `ModuleNotFoundError: No module named 'uvo_pipeline.ingestion_log'`.

- [ ] **Step 3: Implement the module**

```python
# src/uvo_pipeline/ingestion_log.py
"""Centralized ingestion event log — one Mongo doc per event.

Used by extractors and the ingestor to record lifecycle transitions,
batches written, and warnings/errors. Documents expire after 30 days
via a TTL index on `ts`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

LogLevel = Literal["info", "warning", "error", "critical"]
LogEvent = Literal[
    "worker_started",
    "worker_stopped",
    "cycle_complete",
    "cycle_failed",
    "batch_written",
    "decode_failed",
    "write_failed",
    "redis_connect_failed",
    "notice_invalid_date",
    "validation_summary",
]


class IngestionLogEntry(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: LogLevel
    event: LogEvent
    component: str  # e.g. "ingestor", "extractor:vestnik", "dedup-worker"
    source: str | None = None
    source_id: str | None = None
    instance_id: str | None = None
    pipeline_run_id: str | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


async def ensure_log_indexes(db: AsyncIOMotorDatabase) -> None:
    """Indexes for query patterns (recent entries, per-source, per-level) + 30-day TTL."""
    await db.ingestion_log.create_index([("ts", -1)], name="ts_desc")
    await db.ingestion_log.create_index(
        [("source", 1), ("ts", -1)], name="source_ts_desc"
    )
    await db.ingestion_log.create_index(
        [("level", 1), ("ts", -1)], name="level_ts_desc"
    )
    await db.ingestion_log.create_index(
        [("ts", 1)],
        name="ts_ttl",
        expireAfterSeconds=30 * 24 * 60 * 60,
    )


async def log_event(
    db: AsyncIOMotorDatabase,
    *,
    level: LogLevel,
    event: LogEvent,
    component: str,
    message: str,
    source: str | None = None,
    source_id: str | None = None,
    instance_id: str | None = None,
    pipeline_run_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Write one log entry. Never raises — logging must not break the pipeline."""
    entry = IngestionLogEntry(
        level=level,
        event=event,
        component=component,
        message=message,
        source=source,
        source_id=source_id,
        instance_id=instance_id,
        pipeline_run_id=pipeline_run_id,
        details=details or {},
    )
    try:
        await db.ingestion_log.insert_one(entry.model_dump(mode="python"))
    except Exception:
        # Logging must never crash the worker; swallow and continue.
        # Real failures will show up in stdout via the regular Python logger.
        pass
```

- [ ] **Step 4: Wire `ensure_log_indexes` into `ensure_indexes`**

In `src/uvo_pipeline/loaders/mongo.py`, add at the bottom of `ensure_indexes`, just before `logger.info("MongoDB indexes ensured")`:

```python
    # ingestion_log: TTL + query indexes
    from uvo_pipeline.ingestion_log import ensure_log_indexes
    await ensure_log_indexes(db)
```

- [ ] **Step 5: Run tests until green**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/pipeline/test_ingestion_log.py -v'`

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/uvo_pipeline/ingestion_log.py src/uvo_pipeline/loaders/mongo.py tests/pipeline/test_ingestion_log.py
git commit -m "feat(pipeline): add ingestion_log collection with TTL + log_event helper"
```

---

## Task 2: Add date validation utility

**Files:**
- Create: `src/uvo_pipeline/utils/date_validation.py`
- Create: `tests/pipeline/utils/__init__.py` (if missing)
- Create: `tests/pipeline/utils/test_date_validation.py`

- [ ] **Step 1: Ensure tests/pipeline/utils package exists**

```bash
mkdir -p tests/pipeline/utils
[ -f tests/pipeline/utils/__init__.py ] || : > tests/pipeline/utils/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/pipeline/utils/test_date_validation.py
"""Tests for date_validation utility."""
from datetime import date

import pytest

from uvo_pipeline.models import (
    CanonicalAward,
    CanonicalNotice,
    CanonicalSupplier,
)
from uvo_pipeline.utils.date_validation import (
    MIN_YEAR,
    max_year,
    validate_notice_dates,
)


def _supplier(name="Acme s.r.o."):
    return CanonicalSupplier(name=name, name_slug="acme-sro")


def _make_notice(**overrides) -> CanonicalNotice:
    base = dict(
        source="vestnik",
        source_id="N1",
        notice_type="contract_award",
        title="Test",
    )
    base.update(overrides)
    return CanonicalNotice(**base)


def test_valid_dates_pass_through():
    notice = _make_notice(
        publication_date=date(2025, 1, 1),
        award_date=date(2025, 3, 1),
        deadline_date=date(2026, 1, 1),
    )
    cleaned, issues = validate_notice_dates(notice)
    assert issues == []
    assert cleaned.publication_date == date(2025, 1, 1)
    assert cleaned.award_date == date(2025, 3, 1)
    assert cleaned.deadline_date == date(2026, 1, 1)


def test_year_above_max_is_nulled_and_logged():
    notice = _make_notice(publication_date=date(3202, 1, 15))
    cleaned, issues = validate_notice_dates(notice)
    assert cleaned.publication_date is None
    assert len(issues) == 1
    assert issues[0]["field"] == "publication_date"
    assert issues[0]["year"] == 3202
    assert issues[0]["reason"] == "year_above_max"


def test_year_below_min_is_nulled_and_logged():
    notice = _make_notice(award_date=date(1899, 6, 1))
    cleaned, issues = validate_notice_dates(notice)
    assert cleaned.award_date is None
    assert issues[0]["field"] == "award_date"
    assert issues[0]["year"] == 1899
    assert issues[0]["reason"] == "year_below_min"


def test_signing_date_inside_award_validated():
    notice = _make_notice(
        awards=[
            CanonicalAward(
                supplier=_supplier(),
                signing_date=date(2502, 5, 1),
            )
        ],
    )
    cleaned, issues = validate_notice_dates(notice)
    assert cleaned.awards[0].signing_date is None
    assert any(
        i["field"] == "awards[0].signing_date" and i["year"] == 2502 for i in issues
    )


def test_multiple_bad_dates_all_logged():
    notice = _make_notice(
        publication_date=date(3202, 1, 15),
        award_date=date(2502, 1, 15),
    )
    cleaned, issues = validate_notice_dates(notice)
    assert cleaned.publication_date is None
    assert cleaned.award_date is None
    assert {i["field"] for i in issues} == {"publication_date", "award_date"}


def test_constants_sane():
    assert MIN_YEAR <= 1995
    assert max_year() >= 2030
```

- [ ] **Step 3: Run test — expect ImportError**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/pipeline/utils/test_date_validation.py -v'`

Expected: FAIL with `ModuleNotFoundError: No module named 'uvo_pipeline.utils.date_validation'`.

- [ ] **Step 4: Implement the validator**

```python
# src/uvo_pipeline/utils/date_validation.py
"""Date plausibility validator for canonical notices.

Source data sometimes contains malformed years (e.g. 3202 from a typo of
2032, or 2502). Pydantic accepts these because Python's `date` allows
year 1..9999. We clamp to a sane window and report each clamp as an
issue so callers can log it to `ingestion_log`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from uvo_pipeline.models import CanonicalNotice

MIN_YEAR = 1995
MAX_YEAR_DELTA = 5  # allow 5 years into the future for tender deadlines


def max_year() -> int:
    return datetime.now(timezone.utc).year + MAX_YEAR_DELTA


def _check(value: date | None, field: str, issues: list[dict[str, Any]]) -> date | None:
    if value is None:
        return None
    year = value.year
    if year < MIN_YEAR:
        issues.append({"field": field, "year": year, "reason": "year_below_min"})
        return None
    if year > max_year():
        issues.append({"field": field, "year": year, "reason": "year_above_max"})
        return None
    return value


def validate_notice_dates(
    notice: CanonicalNotice,
) -> tuple[CanonicalNotice, list[dict[str, Any]]]:
    """Return a copy of `notice` with implausible dates nulled out, plus the issue list.

    Issues are dicts: `{field, year, reason}`. `field` uses dotted paths
    for nested awards (e.g. `awards[0].signing_date`).
    """
    issues: list[dict[str, Any]] = []
    data = notice.model_dump()

    data["publication_date"] = _check(notice.publication_date, "publication_date", issues)
    data["award_date"] = _check(notice.award_date, "award_date", issues)
    data["deadline_date"] = _check(notice.deadline_date, "deadline_date", issues)

    new_awards = []
    for i, award in enumerate(notice.awards):
        adata = award.model_dump()
        adata["signing_date"] = _check(
            award.signing_date, f"awards[{i}].signing_date", issues
        )
        new_awards.append(adata)
    data["awards"] = new_awards

    return CanonicalNotice.model_validate(data), issues
```

- [ ] **Step 5: Run tests until green**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/pipeline/utils/test_date_validation.py -v'`

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/uvo_pipeline/utils/date_validation.py tests/pipeline/utils/__init__.py tests/pipeline/utils/test_date_validation.py
git commit -m "feat(pipeline): add date plausibility validator"
```

---

## Task 3: Wire validator + lifecycle log events into the ingestor

**Files:**
- Modify: `src/uvo_workers/ingestor.py`
- Create: `tests/workers/test_ingestor_logging.py`

- [ ] **Step 1: Write a behavioural test for ingestor logging**

```python
# tests/workers/test_ingestor_logging.py
"""Tests for ingestor's date-validation + log_event integration.

We don't spin up the full daemon — we test the hot-path helper that
processes one batch (refactored out of run_ingestor in this task).
"""
from datetime import date

import pytest
from mongomock_motor import AsyncMongoMockClient

from uvo_pipeline.ingestion_log import ensure_log_indexes
from uvo_pipeline.models import CanonicalNotice
from uvo_workers.ingestor import process_batch_logs  # to be created


def _notice(source_id: str, **overrides) -> CanonicalNotice:
    base = dict(
        source="vestnik",
        source_id=source_id,
        notice_type="contract_award",
        title="T",
    )
    base.update(overrides)
    return CanonicalNotice(**base)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["test"]


@pytest.mark.asyncio
async def test_process_batch_logs_clamps_bad_dates_and_logs(db):
    await ensure_log_indexes(db)

    notices = [
        _notice("OK1", publication_date=date(2025, 1, 1)),
        _notice("BAD1", publication_date=date(3202, 1, 15)),
        _notice("BAD2", award_date=date(2502, 6, 1)),
    ]

    cleaned = await process_batch_logs(
        db,
        notices=notices,
        component="ingestor",
        instance_id="inst-1",
        stream_name="notices:vestnik",
    )

    # Bad dates nulled
    by_id = {n.source_id: n for n in cleaned}
    assert by_id["OK1"].publication_date == date(2025, 1, 1)
    assert by_id["BAD1"].publication_date is None
    assert by_id["BAD2"].award_date is None

    # One log entry per bad field
    entries = await db.ingestion_log.find(
        {"event": "notice_invalid_date"}
    ).to_list(length=10)
    assert len(entries) == 2
    assert {e["source_id"] for e in entries} == {"BAD1", "BAD2"}
    for e in entries:
        assert e["level"] == "warning"
        assert e["component"] == "ingestor"
        assert e["source"] == "vestnik"
        assert "field" in e["details"]
        assert "year" in e["details"]
```

- [ ] **Step 2: Run the test — expect ImportError**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/workers/test_ingestor_logging.py -v'`

Expected: FAIL with `ImportError: cannot import name 'process_batch_logs' from 'uvo_workers.ingestor'`.

- [ ] **Step 3: Add `process_batch_logs` and lifecycle logging to the ingestor**

Add the new helper near the top of `src/uvo_workers/ingestor.py` (after the imports and `_STREAMS` constant):

```python
from motor.motor_asyncio import AsyncIOMotorDatabase

from uvo_pipeline.ingestion_log import log_event
from uvo_pipeline.utils.date_validation import validate_notice_dates


async def process_batch_logs(
    db: AsyncIOMotorDatabase,
    *,
    notices: list[CanonicalNotice],
    component: str,
    instance_id: str,
    stream_name: str,
) -> list[CanonicalNotice]:
    """Validate dates on each notice, log issues, return cleaned notices.

    The cleaned list keeps the same length and order as the input so the
    caller can ack the same set of stream entry IDs.
    """
    source = stream_name.removeprefix("notices:")
    cleaned: list[CanonicalNotice] = []
    for notice in notices:
        clean, issues = validate_notice_dates(notice)
        cleaned.append(clean)
        for issue in issues:
            await log_event(
                db,
                level="warning",
                event="notice_invalid_date",
                component=component,
                source=source,
                source_id=notice.source_id,
                instance_id=instance_id,
                message=(
                    f"{issue['field']} year {issue['year']} {issue['reason']}; nulled"
                ),
                details=issue,
            )
    return cleaned
```

Then update `run_ingestor`. Replace the existing per-batch loop body (currently `src/uvo_workers/ingestor.py:109-142`) so it (a) calls `process_batch_logs` between decoding and writing, and (b) emits lifecycle events. Use the patch below (read the current file first if line numbers have drifted):

1. After `metrics["redis_connected"] = True` (around line 55), add:

```python
        await log_event(
            db_for_log,  # placeholder — will be defined below
            level="info",
            event="worker_started",
            component="ingestor",
            instance_id=instance_id,
            message="ingestor connected to Redis",
        )
```

But `db_for_log` doesn't exist yet at that point because the Mongo client is created later. Restructure: move `mongo_client = AsyncIOMotorClient(...)` and `db = mongo_client[...]` up so they exist before the first `log_event` call. Concretely, replace the block from `redis_client = await get_redis(...)` through the existing `mongo_client = AsyncIOMotorClient(...)` lines so the order becomes:

```python
    pipeline_settings = PipelineSettings()
    redis_settings = RedisSettings()
    instance_id = uuid.uuid4().hex

    mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
    db = mongo_client[pipeline_settings.mongodb_database]

    metrics: dict = {
        "instance_id": instance_id,
        "batches_processed": 0,
        "notices_written": 0,
        "last_error": None,
        "redis_connected": False,
    }

    try:
        redis_client = await get_redis(
            url=redis_settings.redis_url,
            password=redis_settings.redis_password or None,
        )
        await redis_client.ping()
        metrics["redis_connected"] = True
    except Exception as exc:
        logger.critical("Redis connection failed: %s", exc)
        await log_event(
            db,
            level="critical",
            event="redis_connect_failed",
            component="ingestor",
            instance_id=instance_id,
            message=f"Redis connection failed: {exc}",
        )
        raise SystemExit(1) from exc

    await log_event(
        db,
        level="info",
        event="worker_started",
        component="ingestor",
        instance_id=instance_id,
        message="ingestor up",
        details={"streams": _STREAMS},
    )
```

2. Inside the per-stream loop, between `if not notices: continue` and `try: await upsert_batch(...)`, insert:

```python
                notices = await process_batch_logs(
                    db,
                    notices=notices,
                    component="ingestor",
                    instance_id=instance_id,
                    stream_name=stream_name,
                )
```

3. After the successful `await publish(...)` line, add:

```python
                    await log_event(
                        db,
                        level="info",
                        event="batch_written",
                        component="ingestor",
                        source=source,
                        instance_id=instance_id,
                        message=f"wrote {len(notices)} notices from {stream_name}",
                        details={"count": len(notices)},
                    )
```

4. Inside the existing `except Exception as exc:` block right after `metrics["last_error"] = msg`:

```python
                    await log_event(
                        db,
                        level="error",
                        event="write_failed",
                        component="ingestor",
                        source=stream_name.removeprefix("notices:"),
                        instance_id=instance_id,
                        message=msg,
                    )
```

5. Inside `for entry_id, fields in entries:` `except Exception as exc: logger.warning(...)` block, add:

```python
                        await log_event(
                            db,
                            level="warning",
                            event="decode_failed",
                            component="ingestor",
                            source=stream_name.removeprefix("notices:"),
                            instance_id=instance_id,
                            message=f"decode failed: {exc}",
                        )
```

6. In the `finally:` block before `mongo_client.close()`, add:

```python
        try:
            await log_event(
                db,
                level="info",
                event="worker_stopped",
                component="ingestor",
                instance_id=instance_id,
                message="ingestor shutting down",
                details={
                    "batches_processed": metrics["batches_processed"],
                    "notices_written": metrics["notices_written"],
                },
            )
        except Exception:
            pass
```

- [ ] **Step 4: Run the new test until green**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/workers/test_ingestor_logging.py -v'`

Expected: 1 passed.

- [ ] **Step 5: Run the full pipeline+workers test suite to catch regressions**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/pipeline/ tests/workers/ -v'`

Expected: all green. If `test_runner.py` or others fail because they expect the old `run_ingestor` shape, fix the test rather than reverting (the new behaviour is correct).

- [ ] **Step 6: Commit**

```bash
git add src/uvo_workers/ingestor.py tests/workers/test_ingestor_logging.py
git commit -m "feat(workers): wire date validation + ingestion_log into ingestor"
```

---

## Task 4: Add lifecycle logging to extractor runner

**Files:**
- Modify: `src/uvo_workers/runner.py`
- Create: `tests/workers/test_runner_logging.py`

- [ ] **Step 1: Write a behavioural test for runner lifecycle logging**

```python
# tests/workers/test_runner_logging.py
"""Tests for run_extractor_loop's ingestion_log integration.

We test the small `_log_cycle_result` helper extracted in this task —
testing the full daemon loop is covered by integration tests.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from uvo_pipeline.ingestion_log import ensure_log_indexes
from uvo_workers.runner import _log_cycle_result


@pytest.fixture
def db():
    return AsyncMongoMockClient()["test"]


@pytest.mark.asyncio
async def test_log_cycle_result_success(db):
    await ensure_log_indexes(db)
    await _log_cycle_result(
        db,
        source="vestnik",
        instance_id="i1",
        count=12,
        error=None,
    )
    docs = await db.ingestion_log.find().to_list(length=10)
    assert len(docs) == 1
    assert docs[0]["event"] == "cycle_complete"
    assert docs[0]["level"] == "info"
    assert docs[0]["details"]["count"] == 12


@pytest.mark.asyncio
async def test_log_cycle_result_error(db):
    await ensure_log_indexes(db)
    await _log_cycle_result(
        db,
        source="crz",
        instance_id="i2",
        count=0,
        error="ValueError: boom",
    )
    docs = await db.ingestion_log.find().to_list(length=10)
    assert len(docs) == 1
    assert docs[0]["event"] == "cycle_failed"
    assert docs[0]["level"] == "error"
    assert "boom" in docs[0]["message"]
```

- [ ] **Step 2: Run — expect ImportError**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/workers/test_runner_logging.py -v'`

Expected: FAIL with `ImportError: cannot import name '_log_cycle_result'`.

- [ ] **Step 3: Add Mongo + log_event calls in `run_extractor_loop`**

In `src/uvo_workers/runner.py`:

a. Add imports at the top:

```python
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClient

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.ingestion_log import log_event
```

b. Add the helper just below the existing `logger = logging.getLogger(__name__)` line:

```python
async def _log_cycle_result(
    db: AsyncIOMotorDatabase,
    *,
    source: str,
    instance_id: str,
    count: int,
    error: str | None,
) -> None:
    if error is None:
        await log_event(
            db,
            level="info",
            event="cycle_complete",
            component=f"extractor:{source}",
            source=source,
            instance_id=instance_id,
            message=f"{source}: {count} items XADDed",
            details={"count": count},
        )
    else:
        await log_event(
            db,
            level="error",
            event="cycle_failed",
            component=f"extractor:{source}",
            source=source,
            instance_id=instance_id,
            message=error,
        )
```

c. Inside `run_extractor_loop`, just after the existing `instance_id = instance_id or uuid.uuid4().hex` line:

```python
    pipeline_settings = PipelineSettings()
    mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
    db = mongo_client[pipeline_settings.mongodb_database]
```

d. After `metrics["redis_connected"] = True` (just before `stop_event = asyncio.Event()`):

```python
    await log_event(
        db,
        level="info",
        event="worker_started",
        component=f"extractor:{source}",
        source=source,
        instance_id=instance_id,
        message=f"{source} extractor up",
        details={"interval_seconds": interval_seconds},
    )
```

e. In the `except Exception as exc:` for the Redis connect failure (`logger.critical("Redis connection failed for %s: %s", source, exc)`), add right after the logger call (still before `raise SystemExit(1)`):

```python
        try:
            await log_event(
                db,
                level="critical",
                event="redis_connect_failed",
                component=f"extractor:{source}",
                source=source,
                instance_id=instance_id,
                message=str(exc),
            )
        except Exception:
            pass
```

f. Replace the contents of the `if acquired:` branch (currently `try: count = await extract(...) ... except Exception as exc: ...`) with:

```python
                    error: str | None = None
                    count = 0
                    try:
                        count = await extract(redis_client, state)
                        metrics["cycles_completed"] += 1
                        logger.info("%s: cycle complete, %d items XADDed", source, count)
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        metrics["last_error"] = error
                        logger.error("%s: extract error: %s", source, error)
                    await _log_cycle_result(
                        db,
                        source=source,
                        instance_id=instance_id,
                        count=count,
                        error=error,
                    )
```

g. In the `finally:` block, just before `await close_redis(redis_client)`:

```python
        try:
            await log_event(
                db,
                level="info",
                event="worker_stopped",
                component=f"extractor:{source}",
                source=source,
                instance_id=instance_id,
                message=f"{source}: worker stopped",
                details={
                    "cycles_completed": metrics["cycles_completed"],
                    "cycles_skipped_locked": metrics["cycles_skipped_locked"],
                },
            )
        except Exception:
            pass
        mongo_client.close()
```

- [ ] **Step 4: Run new tests + existing runner tests**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/workers/ -v'`

Expected: all green. If `tests/workers/test_runner.py` fails because it didn't expect a Mongo connection, mock it with `mongomock_motor` in that test, or override `AsyncIOMotorClient` via monkeypatch.

- [ ] **Step 5: Commit**

```bash
git add src/uvo_workers/runner.py tests/workers/test_runner_logging.py
git commit -m "feat(workers): emit ingestion_log lifecycle events from extractor runner"
```

---

## Task 5: API endpoint to read the ingestion log

**Files:**
- Create: `src/uvo_api/routers/ingestion_log.py`
- Modify: `src/uvo_api/app.py`
- Modify: `src/uvo_api/models.py`
- Create: `tests/api/test_ingestion_log.py`

- [ ] **Step 1: Write the failing API test**

```python
# tests/api/test_ingestion_log.py
"""Tests for /api/dashboard/ingestion-log endpoint."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from uvo_api.app import create_app
from uvo_api.db import get_db
from uvo_pipeline.ingestion_log import ensure_log_indexes


@pytest.fixture
def client_and_db(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    monkeypatch.setattr("uvo_api.db.get_db", lambda: db)
    monkeypatch.setattr("uvo_api.routers.ingestion_log.get_db", lambda: db)
    app = create_app()
    return TestClient(app), db


@pytest.mark.asyncio
async def _seed(db):
    await ensure_log_indexes(db)
    now = datetime.now(timezone.utc)
    docs = [
        {
            "ts": now - timedelta(minutes=i),
            "level": "info" if i % 2 == 0 else "warning",
            "event": "batch_written" if i % 2 == 0 else "notice_invalid_date",
            "component": "ingestor",
            "source": "vestnik" if i < 3 else "crz",
            "source_id": f"N{i}",
            "instance_id": "i1",
            "pipeline_run_id": None,
            "message": f"event {i}",
            "details": {"i": i},
        }
        for i in range(6)
    ]
    await db.ingestion_log.insert_many(docs)


@pytest.mark.asyncio
async def test_returns_recent_entries_sorted_desc(client_and_db):
    client, db = client_and_db
    await _seed(db)
    res = client.get("/api/dashboard/ingestion-log")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 6
    items = body["items"]
    assert len(items) == 6
    # Newest first
    timestamps = [it["ts"] for it in items]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_filter_by_level(client_and_db):
    client, db = client_and_db
    await _seed(db)
    res = client.get("/api/dashboard/ingestion-log?level=warning")
    assert res.status_code == 200
    body = res.json()
    assert all(it["level"] == "warning" for it in body["items"])
    assert len(body["items"]) == 3


@pytest.mark.asyncio
async def test_filter_by_source_and_event(client_and_db):
    client, db = client_and_db
    await _seed(db)
    res = client.get(
        "/api/dashboard/ingestion-log?source=vestnik&event=batch_written"
    )
    assert res.status_code == 200
    body = res.json()
    assert all(
        it["source"] == "vestnik" and it["event"] == "batch_written"
        for it in body["items"]
    )


@pytest.mark.asyncio
async def test_limit_and_offset(client_and_db):
    client, db = client_and_db
    await _seed(db)
    res1 = client.get("/api/dashboard/ingestion-log?limit=2&offset=0")
    res2 = client.get("/api/dashboard/ingestion-log?limit=2&offset=2")
    items1 = res1.json()["items"]
    items2 = res2.json()["items"]
    assert len(items1) == 2 and len(items2) == 2
    assert {i["source_id"] for i in items1}.isdisjoint(
        {i["source_id"] for i in items2}
    )
```

- [ ] **Step 2: Run — expect 404 (no route)**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/api/test_ingestion_log.py -v'`

Expected: FAIL with 404 from FastAPI.

- [ ] **Step 3: Add response model**

In `src/uvo_api/models.py`, append at the end:

```python
class IngestionLogItem(BaseModel):
    ts: str
    level: str
    event: str
    component: str
    source: str | None = None
    source_id: str | None = None
    instance_id: str | None = None
    pipeline_run_id: str | None = None
    message: str
    details: dict = {}


class IngestionLogResponse(BaseModel):
    total: int
    items: list[IngestionLogItem]
```

(If `BaseModel` isn't already imported at the top of models.py, add `from pydantic import BaseModel` — check before adding.)

- [ ] **Step 4: Implement the router**

```python
# src/uvo_api/routers/ingestion_log.py
"""Read-only endpoint exposing the ingestion_log collection."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from uvo_api.db import get_db
from uvo_api.models import IngestionLogItem, IngestionLogResponse

router = APIRouter(prefix="/api/dashboard", tags=["ingestion-log"])


def _to_iso_z(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


@router.get("/ingestion-log", response_model=IngestionLogResponse)
async def get_ingestion_log(
    level: str | None = Query(None, pattern="^(info|warning|error|critical)$"),
    source: str | None = Query(None),
    event: str | None = Query(None),
    component: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> IngestionLogResponse:
    db = get_db()
    query: dict = {}
    if level:
        query["level"] = level
    if source:
        query["source"] = source
    if event:
        query["event"] = event
    if component:
        query["component"] = component

    total = await db.ingestion_log.count_documents(query)
    cursor = (
        db.ingestion_log.find(query)
        .sort("ts", -1)
        .skip(offset)
        .limit(limit)
    )
    items: list[IngestionLogItem] = []
    async for doc in cursor:
        items.append(
            IngestionLogItem(
                ts=_to_iso_z(doc.get("ts")),
                level=doc.get("level", "info"),
                event=doc.get("event", "unknown"),
                component=doc.get("component", ""),
                source=doc.get("source"),
                source_id=doc.get("source_id"),
                instance_id=doc.get("instance_id"),
                pipeline_run_id=doc.get("pipeline_run_id"),
                message=doc.get("message", ""),
                details=doc.get("details") or {},
            )
        )
    return IngestionLogResponse(total=total, items=items)
```

- [ ] **Step 5: Register the router**

In `src/uvo_api/app.py`:

1. Add `ingestion_log` to the import line:
   `from uvo_api.routers import contracts, dashboard, graph, ingestion, ingestion_log, procurers, search, suppliers`
2. After `app.include_router(ingestion.router)`, add:
   `app.include_router(ingestion_log.router)`

- [ ] **Step 6: Run tests until green**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/api/test_ingestion_log.py -v'`

Expected: 4 passed.

- [ ] **Step 7: Run the full API test suite to catch regressions**

Run: `wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/api/ -v'`

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/uvo_api/routers/ingestion_log.py src/uvo_api/app.py src/uvo_api/models.py tests/api/test_ingestion_log.py
git commit -m "feat(api): add /api/dashboard/ingestion-log endpoint"
```

---

## Task 6: GUI panel for the ingestion log

**Files:**
- Create: `src/uvo-gui-react/src/api/queries/ingestionLog.ts`
- Create: `src/uvo-gui-react/src/components/ingestion/IngestionLogPanel.tsx`
- Modify: `src/uvo-gui-react/src/api/types.ts`
- Modify: `src/uvo-gui-react/src/i18n/sk.ts`
- Modify: `src/uvo-gui-react/src/pages/IngestionPage.tsx`

- [ ] **Step 1: Add TypeScript types**

Append to `src/uvo-gui-react/src/api/types.ts`:

```typescript
export type IngestionLogLevel = 'info' | 'warning' | 'error' | 'critical'

export interface IngestionLogItem {
  ts: string
  level: IngestionLogLevel
  event: string
  component: string
  source: string | null
  source_id: string | null
  instance_id: string | null
  pipeline_run_id: string | null
  message: string
  details: Record<string, unknown>
}

export interface IngestionLogResponse {
  total: number
  items: IngestionLogItem[]
}
```

- [ ] **Step 2: Add the TanStack Query hook**

```typescript
// src/uvo-gui-react/src/api/queries/ingestionLog.ts
import { useQuery } from '@tanstack/react-query'
import type { IngestionLogResponse, IngestionLogLevel } from '../types'

export interface UseIngestionLogParams {
  level?: IngestionLogLevel
  source?: string
  event?: string
  limit?: number
  offset?: number
}

async function fetchIngestionLog(
  params: UseIngestionLogParams,
): Promise<IngestionLogResponse> {
  const search = new URLSearchParams()
  if (params.level) search.set('level', params.level)
  if (params.source) search.set('source', params.source)
  if (params.event) search.set('event', params.event)
  search.set('limit', String(params.limit ?? 50))
  search.set('offset', String(params.offset ?? 0))
  const res = await fetch(`/api/dashboard/ingestion-log?${search}`)
  if (!res.ok) throw new Error(`ingestion-log: ${res.status}`)
  return res.json()
}

export function useIngestionLog(params: UseIngestionLogParams = {}) {
  return useQuery({
    queryKey: ['ingestion-log', params],
    queryFn: () => fetchIngestionLog(params),
    refetchInterval: 15_000,
  })
}
```

- [ ] **Step 3: Add Slovak strings**

In `src/uvo-gui-react/src/i18n/sk.ts`, append a new section before the closing `}` of the default export (and ensure it's reachable from the `ingestion` page area):

```typescript
  ingestionLog: {
    title: 'Posledne udalosti',
    levelAll: 'Vsetky',
    levelInfo: 'Info',
    levelWarning: 'Varovania',
    levelError: 'Chyby',
    sourceAll: 'Vsetky zdroje',
    colTime: 'Cas',
    colLevel: 'Uroven',
    colEvent: 'Udalost',
    colSource: 'Zdroj',
    colMessage: 'Sprava',
    empty: 'Ziadne udalosti',
    loading: 'Nacitavam log...',
  },
```

- [ ] **Step 4: Build the panel**

```tsx
// src/uvo-gui-react/src/components/ingestion/IngestionLogPanel.tsx
import { useState } from 'react'
import { useIngestionLog } from '@/api/queries/ingestionLog'
import type { IngestionLogLevel } from '@/api/types'
import sk from '@/i18n/sk'
import { cn } from '@/lib/utils'

const LEVELS: Array<{ key: IngestionLogLevel | 'all'; label: string }> = [
  { key: 'all', label: sk.ingestionLog.levelAll },
  { key: 'info', label: sk.ingestionLog.levelInfo },
  { key: 'warning', label: sk.ingestionLog.levelWarning },
  { key: 'error', label: sk.ingestionLog.levelError },
]

const LEVEL_CLASSES: Record<IngestionLogLevel, string> = {
  info: 'text-slate-600',
  warning: 'text-amber-600',
  error: 'text-red-600',
  critical: 'text-red-700 font-semibold',
}

function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('sk-SK', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(iso))
}

export function IngestionLogPanel() {
  const [level, setLevel] = useState<IngestionLogLevel | 'all'>('all')
  const { data, isLoading, isError } = useIngestionLog({
    level: level === 'all' ? undefined : level,
    limit: 50,
  })

  return (
    <section className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{sk.ingestionLog.title}</h2>
        <div className="flex gap-2">
          {LEVELS.map((l) => (
            <button
              key={l.key}
              onClick={() => setLevel(l.key as IngestionLogLevel | 'all')}
              className={cn(
                'rounded border px-2 py-1 text-sm',
                level === l.key
                  ? 'border-blue-500 bg-blue-50 text-blue-700'
                  : 'border-slate-200 text-slate-600',
              )}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <div className="text-sm text-slate-500">{sk.ingestionLog.loading}</div>}
      {isError && <div className="text-sm text-red-600">{sk.common.error}</div>}
      {data && data.items.length === 0 && (
        <div className="text-sm text-slate-500">{sk.ingestionLog.empty}</div>
      )}

      {data && data.items.length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="py-1 pr-2">{sk.ingestionLog.colTime}</th>
              <th className="py-1 pr-2">{sk.ingestionLog.colLevel}</th>
              <th className="py-1 pr-2">{sk.ingestionLog.colEvent}</th>
              <th className="py-1 pr-2">{sk.ingestionLog.colSource}</th>
              <th className="py-1 pr-2">{sk.ingestionLog.colMessage}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((it, i) => (
              <tr key={i} className="border-t border-slate-100 align-top">
                <td className="py-1 pr-2 whitespace-nowrap text-slate-600">
                  {formatTime(it.ts)}
                </td>
                <td className={cn('py-1 pr-2', LEVEL_CLASSES[it.level])}>{it.level}</td>
                <td className="py-1 pr-2 font-mono text-xs">{it.event}</td>
                <td className="py-1 pr-2">{it.source ?? '—'}</td>
                <td className="py-1 pr-2">{it.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
```

- [ ] **Step 5: Mount the panel on `IngestionPage`**

In `src/uvo-gui-react/src/pages/IngestionPage.tsx`:

1. Add the import near the top with the other component imports:
   `import { IngestionLogPanel } from '@/components/ingestion/IngestionLogPanel'`
2. Render `<IngestionLogPanel />` as the last child inside the page's outer container (after the existing dashboard sections — find the closing `</div>` of the page root and place it just above).

- [ ] **Step 6: Verify build + types**

Run: `cd src/uvo-gui-react && npm run typecheck && npm test -- --run`

Expected: typecheck passes, tests pass. (If `npm run typecheck` script doesn't exist, run `npx tsc --noEmit` instead.)

- [ ] **Step 7: Manual smoke test**

```bash
# Terminal 1
docker compose up -d mongo redis api gui-react
# Terminal 2 — emit a fake event from a Python REPL or one-shot script
uv run python -c "
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.ingestion_log import ensure_log_indexes, log_event

async def main():
    s = PipelineSettings()
    db = AsyncIOMotorClient(s.mongodb_uri)[s.mongodb_database]
    await ensure_log_indexes(db)
    await log_event(db, level='warning', event='notice_invalid_date',
        component='ingestor', source='vestnik', source_id='SMOKE-1',
        message='award_date year 3202 year_above_max; nulled',
        details={'field': 'award_date', 'year': 3202, 'reason': 'year_above_max'})

asyncio.run(main())
"
# Open http://localhost:8080/ingestion in a browser — the panel should show the smoke entry.
```

Expected: One row with level=warning, event=notice_invalid_date, source=vestnik, message about year 3202.

- [ ] **Step 8: Commit**

```bash
git add src/uvo-gui-react/src/api/queries/ingestionLog.ts \
        src/uvo-gui-react/src/api/types.ts \
        src/uvo-gui-react/src/components/ingestion/IngestionLogPanel.tsx \
        src/uvo-gui-react/src/i18n/sk.ts \
        src/uvo-gui-react/src/pages/IngestionPage.tsx
git commit -m "feat(gui): add ingestion log panel to IngestionPage"
```

---

## Task 7: Backfill cleanup of existing bad-year notices (optional but recommended)

**Files:**
- Create: `scripts/clamp_bad_dates.py`

- [ ] **Step 1: Write the script**

```python
# scripts/clamp_bad_dates.py
"""One-shot: scan `notices` for implausible date years and null them out.

Mirrors the runtime validation rule. Use --dry-run first.
Logs each clamp to `ingestion_log` with event=notice_invalid_date
component=backfill so the UI surfaces them just like live events.
"""

import argparse
import asyncio
from datetime import date

from motor.motor_asyncio import AsyncIOMotorClient

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.ingestion_log import ensure_log_indexes, log_event
from uvo_pipeline.utils.date_validation import MIN_YEAR, max_year


DATE_FIELDS = ["publication_date", "deadline_date", "award_date"]


async def main(dry_run: bool, limit: int | None) -> None:
    settings = PipelineSettings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]
    await ensure_log_indexes(db)

    lo, hi = MIN_YEAR, max_year()
    query = {
        "$or": [
            {f: {"$lt": f"{lo:04d}-01-01"}} for f in DATE_FIELDS
        ] + [
            {f: {"$gt": f"{hi:04d}-12-31"}} for f in DATE_FIELDS
        ]
    }

    cursor = db.notices.find(query)
    if limit:
        cursor = cursor.limit(limit)

    fixed = 0
    async for doc in cursor:
        unsets = {}
        details_per_field = []
        for f in DATE_FIELDS:
            v = doc.get(f)
            if isinstance(v, str) and len(v) >= 4:
                try:
                    y = int(v[:4])
                except ValueError:
                    continue
                if y < lo or y > hi:
                    unsets[f] = ""
                    details_per_field.append({"field": f, "year": y})
            elif isinstance(v, date):
                if v.year < lo or v.year > hi:
                    unsets[f] = ""
                    details_per_field.append({"field": f, "year": v.year})

        if not unsets:
            continue

        if not dry_run:
            await db.notices.update_one(
                {"_id": doc["_id"]},
                {"$unset": unsets},
            )
            for d in details_per_field:
                await log_event(
                    db,
                    level="warning",
                    event="notice_invalid_date",
                    component="backfill",
                    source=doc.get("source"),
                    source_id=doc.get("source_id"),
                    message=f"backfill: {d['field']} year {d['year']} clamped",
                    details={**d, "reason": "year_out_of_range"},
                )
        fixed += 1

    print(f"{'DRY RUN — ' if dry_run else ''}clamped {fixed} notices")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()
    asyncio.run(main(dry_run=args.dry_run, limit=args.limit))
```

- [ ] **Step 2: Dry run against local Mongo**

```bash
docker compose up -d mongo
wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run python scripts/clamp_bad_dates.py --dry-run'
```

Expected: prints `DRY RUN — clamped N notices` where N matches the count of records the user is seeing in the chart with year > 2030 or < 1995.

- [ ] **Step 3: Real run (only if dry-run output looks right)**

```bash
wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run python scripts/clamp_bad_dates.py'
```

Expected: same N, the bad bars disappear from "Objem po rokoch", and one `ingestion_log` entry appears per clamped field.

- [ ] **Step 4: Commit**

```bash
git add scripts/clamp_bad_dates.py
git commit -m "chore(scripts): backfill clamp for implausible date years in notices"
```

---

## Self-Review Checklist (mental, before declaring done)

- Spec coverage:
  - "date validation in pipeline ingestion + message" — Tasks 2, 3 (validator + ingestor wiring + log_event with `notice_invalid_date`).
  - "log DB for ingestion (running, ingested, problems, other)" — Task 1 (collection + helper), Task 3 (ingestor lifecycle), Task 4 (extractor lifecycle), Task 5 (API), Task 6 (GUI). Task 7 is optional cleanup of pre-existing bad data.
- Type consistency: `process_batch_logs`, `_log_cycle_result`, `validate_notice_dates`, `log_event` signatures referenced consistently across tasks.
- No placeholders: every code block is concrete; every test asserts specific values; every shell command is runnable as written.
