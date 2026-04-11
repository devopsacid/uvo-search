# Deduplication & Ingestion Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pre-ingestion skip check, a durable `ingested_docs` audit registry, content hashing for change detection, and an enhanced cross-source dedup pass for ICO-less notices.

**Architecture:** A new `ingested_docs` MongoDB collection acts as a fast lookup set — before each batch upsert, hashes are compared against the registry so unchanged documents are skipped entirely. A new `utils/hashing.py` module computes a stable SHA-256 fingerprint per notice. The existing cross-source dedup in the orchestrator gains a second pass matching on `(title_slug, publication_date ±7d)` for notices missing ICO.

**Tech Stack:** Python 3.12, Motor (async MongoDB), Pydantic v2, pytest, hashlib (stdlib)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/uvo_pipeline/utils/hashing.py` | `compute_notice_hash(notice) -> str` — stable SHA-256 from key fields |
| Modify | `src/uvo_pipeline/models.py` | Add `content_hash` to `CanonicalNotice`; add `notices_skipped` to `PipelineReport` |
| Modify | `src/uvo_pipeline/loaders/mongo.py` | `ensure_indexes`: add `ingested_docs` indexes; `upsert_batch`: pre-ingestion check + registry writes |
| Modify | `src/uvo_pipeline/orchestrator.py` | Compute hashes before upsert; propagate `skipped` to report; add Pass 2 to `_run_cross_source_dedup` |
| Create | `tests/pipeline/test_dedup.py` | Unit tests for hash stability, skip logic, Pass 2 cross-source match |

---

### Task 1: Content Hash Utility

**Files:**
- Create: `src/uvo_pipeline/utils/hashing.py`
- Test: `tests/pipeline/test_dedup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_dedup.py`:

```python
"""Tests for deduplication and ingestion registry."""
from datetime import date

import pytest

from uvo_pipeline.models import CanonicalNotice, CanonicalProcurer, CanonicalAddress
from uvo_pipeline.utils.hashing import compute_notice_hash


def _make_notice(**kwargs) -> CanonicalNotice:
    defaults = dict(
        source="uvo",
        source_id="UVO-001",
        notice_type="contract_notice",
        title="Test Notice",
        procurer=CanonicalProcurer(
            ico="12345678",
            name="Test Procurer",
            name_slug="test-procurer",
        ),
        cpv_code="45000000",
        publication_date=date(2026, 1, 15),
        estimated_value=100_000.0,
    )
    defaults.update(kwargs)
    return CanonicalNotice(**defaults)


def test_hash_is_deterministic():
    n = _make_notice()
    assert compute_notice_hash(n) == compute_notice_hash(n)


def test_hash_changes_when_title_changes():
    n1 = _make_notice(title="Original Title")
    n2 = _make_notice(title="Changed Title")
    assert compute_notice_hash(n1) != compute_notice_hash(n2)


def test_hash_changes_when_value_changes():
    n1 = _make_notice(estimated_value=100_000.0)
    n2 = _make_notice(estimated_value=200_000.0)
    assert compute_notice_hash(n1) != compute_notice_hash(n2)


def test_hash_stable_across_irrelevant_fields():
    """Fields like ingested_at and pipeline_run_id must NOT affect the hash."""
    n1 = _make_notice()
    n1.pipeline_run_id = "run-aaa"
    n2 = _make_notice()
    n2.pipeline_run_id = "run-bbb"
    assert compute_notice_hash(n1) == compute_notice_hash(n2)


def test_hash_none_procurer():
    n = _make_notice(procurer=None)
    h = compute_notice_hash(n)
    assert h.startswith("sha256:")


def test_hash_returns_sha256_prefix():
    n = _make_notice()
    h = compute_notice_hash(n)
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/max/Documents/src/uvo-search
pytest tests/pipeline/test_dedup.py -v 2>&1 | head -30
```

Expected: `ImportError` — `cannot import name 'compute_notice_hash'`

- [ ] **Step 3: Implement `hashing.py`**

Create `src/uvo_pipeline/utils/hashing.py`:

```python
"""Stable content hash for CanonicalNotice deduplication."""

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uvo_pipeline.models import CanonicalNotice


def compute_notice_hash(notice: "CanonicalNotice") -> str:
    """Return a stable SHA-256 fingerprint of the notice's key fields.

    Only fields that indicate a meaningful content change are included.
    Metadata fields (ingested_at, pipeline_run_id, canonical_id) are excluded.
    """
    parts = [
        notice.source,
        notice.source_id,
        notice.title or "",
        notice.procurer.ico if notice.procurer and notice.procurer.ico else "",
        notice.cpv_code or "",
        str(notice.publication_date) if notice.publication_date else "",
        str(notice.estimated_value) if notice.estimated_value is not None else "",
    ]
    raw = "|".join(parts).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return f"sha256:{digest}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/pipeline/test_dedup.py::test_hash_is_deterministic \
       tests/pipeline/test_dedup.py::test_hash_changes_when_title_changes \
       tests/pipeline/test_dedup.py::test_hash_changes_when_value_changes \
       tests/pipeline/test_dedup.py::test_hash_stable_across_irrelevant_fields \
       tests/pipeline/test_dedup.py::test_hash_none_procurer \
       tests/pipeline/test_dedup.py::test_hash_returns_sha256_prefix \
       -v
```

Expected: All 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/uvo_pipeline/utils/hashing.py tests/pipeline/test_dedup.py
git commit -m "feat: add content hash utility for notice deduplication"
```

---

### Task 2: Model Updates

**Files:**
- Modify: `src/uvo_pipeline/models.py`

- [ ] **Step 1: Write failing test**

Add to `tests/pipeline/test_dedup.py`:

```python
def test_canonical_notice_has_content_hash_field():
    n = _make_notice()
    assert hasattr(n, "content_hash")
    assert n.content_hash is None  # default


def test_pipeline_report_has_notices_skipped():
    from datetime import datetime
    from uvo_pipeline.models import PipelineReport
    r = PipelineReport(run_id="x", mode="recent", started_at=datetime.utcnow())
    assert r.notices_skipped == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/pipeline/test_dedup.py::test_canonical_notice_has_content_hash_field \
       tests/pipeline/test_dedup.py::test_pipeline_report_has_notices_skipped -v
```

Expected: FAIL — `AttributeError` or assertion error.

- [ ] **Step 3: Add fields to models**

In `src/uvo_pipeline/models.py`, add `content_hash` to `CanonicalNotice` after `pipeline_run_id`:

```python
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    pipeline_run_id: str | None = None
    content_hash: str | None = None
```

Add `notices_skipped` to `PipelineReport`:

```python
class PipelineReport(BaseModel):
    """Summary returned by the orchestrator after a pipeline run."""
    run_id: str
    mode: str
    started_at: datetime
    finished_at: datetime | None = None
    notices_inserted: int = 0
    notices_updated: int = 0
    notices_skipped: int = 0
    errors: list[str] = []
    source_counts: dict[str, int] = {}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/pipeline/test_dedup.py -v
```

Expected: All 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/uvo_pipeline/models.py tests/pipeline/test_dedup.py
git commit -m "feat: add content_hash to CanonicalNotice and notices_skipped to PipelineReport"
```

---

### Task 3: `ingested_docs` Indexes

**Files:**
- Modify: `src/uvo_pipeline/loaders/mongo.py`

- [ ] **Step 1: Write failing test**

Add to `tests/pipeline/test_dedup.py`:

```python
@pytest.mark.asyncio
async def test_ensure_indexes_creates_ingested_docs_indexes(motor_db):
    """ensure_indexes must create required indexes on ingested_docs collection."""
    from uvo_pipeline.loaders.mongo import ensure_indexes

    await ensure_indexes(motor_db)

    index_names = await motor_db.ingested_docs.index_information()
    assert "source_source_id_unique" in index_names
    assert index_names["source_source_id_unique"]["unique"] is True
    assert "pipeline_run_id" in index_names
    assert "source_ingested_at_desc" in index_names
```

This test requires a `motor_db` fixture. Add to `tests/pipeline/conftest.py` (or create it if it doesn't exist):

```python
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient


@pytest_asyncio.fixture
async def motor_db():
    """Temporary in-memory-style MongoDB for tests (uses mongomock-motor or real local Mongo)."""
    import os
    uri = os.getenv("TEST_MONGODB_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(uri)
    db = client["uvo_test_tmp"]
    yield db
    await client.drop_database("uvo_test_tmp")
    client.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/pipeline/test_dedup.py::test_ensure_indexes_creates_ingested_docs_indexes -v
```

Expected: FAIL — `AssertionError` (indexes not yet created).

- [ ] **Step 3: Add `ingested_docs` indexes to `ensure_indexes`**

In `src/uvo_pipeline/loaders/mongo.py`, add at the end of `ensure_indexes` (before the final `logger.info`):

```python
    # ingested_docs: unique on (source, source_id), queryable by run and time
    await db.ingested_docs.create_index(
        [("source", 1), ("source_id", 1)],
        unique=True,
        name="source_source_id_unique",
    )
    await db.ingested_docs.create_index(
        [("pipeline_run_id", 1)],
        name="pipeline_run_id",
    )
    await db.ingested_docs.create_index(
        [("source", 1), ("ingested_at", -1)],
        name="source_ingested_at_desc",
    )
    await db.ingested_docs.create_index(
        [("ingested_at", -1)],
        name="ingested_at_desc",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/pipeline/test_dedup.py::test_ensure_indexes_creates_ingested_docs_indexes -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/uvo_pipeline/loaders/mongo.py tests/pipeline/test_dedup.py tests/pipeline/conftest.py
git commit -m "feat: add ingested_docs indexes to ensure_indexes"
```

---

### Task 4: Pre-Ingestion Skip in `upsert_batch`

**Files:**
- Modify: `src/uvo_pipeline/loaders/mongo.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/pipeline/test_dedup.py`:

```python
@pytest.mark.asyncio
async def test_upsert_batch_inserts_new_notices(motor_db):
    from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch

    await ensure_indexes(motor_db)
    notices = [_make_notice(source_id="N-001"), _make_notice(source_id="N-002")]
    result = await upsert_batch(motor_db, notices)

    assert result["inserted"] == 2
    assert result["updated"] == 0
    assert result["skipped"] == 0
    assert result["errors"] == 0

    registry_count = await motor_db.ingested_docs.count_documents({})
    assert registry_count == 2


@pytest.mark.asyncio
async def test_upsert_batch_skips_unchanged_notices(motor_db):
    from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch

    await ensure_indexes(motor_db)
    notices = [_make_notice(source_id="N-001")]

    # First run — insert
    r1 = await upsert_batch(motor_db, notices)
    assert r1["inserted"] == 1

    # Second run — same content, should be skipped
    r2 = await upsert_batch(motor_db, notices)
    assert r2["inserted"] == 0
    assert r2["updated"] == 0
    assert r2["skipped"] == 1

    # skipped_count incremented in registry
    reg = await motor_db.ingested_docs.find_one({"source": "uvo", "source_id": "N-001"})
    assert reg["skipped_count"] == 1


@pytest.mark.asyncio
async def test_upsert_batch_updates_changed_notices(motor_db):
    from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch

    await ensure_indexes(motor_db)
    n1 = _make_notice(source_id="N-001", title="Original")
    await upsert_batch(motor_db, [n1])

    n2 = _make_notice(source_id="N-001", title="Updated Title")
    r = await upsert_batch(motor_db, [n2])
    assert r["updated"] == 1
    assert r["skipped"] == 0

    doc = await motor_db.notices.find_one({"source": "uvo", "source_id": "N-001"})
    assert doc["title"] == "Updated Title"

    reg = await motor_db.ingested_docs.find_one({"source": "uvo", "source_id": "N-001"})
    assert reg["content_hash"] != compute_notice_hash(n1)
    assert reg["content_hash"] == compute_notice_hash(n2)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/pipeline/test_dedup.py::test_upsert_batch_inserts_new_notices \
       tests/pipeline/test_dedup.py::test_upsert_batch_skips_unchanged_notices \
       tests/pipeline/test_dedup.py::test_upsert_batch_updates_changed_notices -v
```

Expected: FAIL — `KeyError: 'skipped'` (return dict missing key).

- [ ] **Step 3: Rewrite `upsert_batch` with pre-ingestion check**

Replace the entire `upsert_batch` function in `src/uvo_pipeline/loaders/mongo.py`:

```python
async def upsert_batch(
    db: AsyncIOMotorDatabase,
    notices: list[CanonicalNotice],
    *,
    batch_size: int = 500,
) -> dict[str, int]:
    """Bulk upsert a list of notices with pre-ingestion skip for unchanged docs.

    Returns {inserted, updated, skipped, errors}.
    """
    from uvo_pipeline.utils.hashing import compute_notice_hash

    # Compute hashes for all notices
    for notice in notices:
        if notice.content_hash is None:
            notice.content_hash = compute_notice_hash(notice)

    inserted = updated = skipped = errors = 0

    for i in range(0, len(notices), batch_size):
        batch = notices[i : i + batch_size]

        # Bulk-fetch existing registry entries for this batch
        keys = [{"source": n.source, "source_id": n.source_id} for n in batch]
        existing: dict[tuple[str, str], str] = {}
        async for reg in db.ingested_docs.find({"$or": keys}):
            existing[(reg["source"], reg["source_id"])] = reg["content_hash"]

        for notice in batch:
            key = (notice.source, notice.source_id)
            stored_hash = existing.get(key)

            if stored_hash == notice.content_hash:
                # Unchanged — skip DB write, update last_seen_at
                try:
                    await db.ingested_docs.update_one(
                        {"source": notice.source, "source_id": notice.source_id},
                        {
                            "$set": {"last_seen_at": notice.ingested_at},
                            "$inc": {"skipped_count": 1},
                        },
                    )
                    skipped += 1
                except Exception as exc:
                    logger.warning("Failed to update registry for %s/%s: %s", notice.source, notice.source_id, exc)
                continue

            # New or changed — upsert the notice
            try:
                doc = notice.model_dump(mode="json")
                result = await db.notices.update_one(
                    {"source": notice.source, "source_id": notice.source_id},
                    {
                        "$set": {k: v for k, v in doc.items() if k != "ingested_at"},
                        "$setOnInsert": {"ingested_at": doc["ingested_at"]},
                    },
                    upsert=True,
                )
                if result.upserted_id:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:
                logger.error("Failed to upsert notice %s/%s: %s", notice.source, notice.source_id, exc)
                errors += 1
                continue

            # Update ingestion registry
            try:
                await db.ingested_docs.update_one(
                    {"source": notice.source, "source_id": notice.source_id},
                    {
                        "$set": {
                            "source": notice.source,
                            "source_id": notice.source_id,
                            "content_hash": notice.content_hash,
                            "last_seen_at": notice.ingested_at,
                            "pipeline_run_id": notice.pipeline_run_id,
                        },
                        "$setOnInsert": {
                            "ingested_at": notice.ingested_at,
                            "skipped_count": 0,
                        },
                    },
                    upsert=True,
                )
            except Exception as exc:
                logger.warning("Failed to write registry for %s/%s: %s", notice.source, notice.source_id, exc)

        # Upsert entities from this batch (procurers, suppliers)
        for notice in batch:
            if notice.procurer:
                try:
                    await upsert_procurer(db, notice.procurer)
                except Exception as exc:
                    logger.warning("Failed to upsert procurer: %s", exc)
            for award in notice.awards:
                try:
                    await upsert_supplier(db, award.supplier)
                except Exception as exc:
                    logger.warning("Failed to upsert supplier: %s", exc)

    logger.info(
        "Batch upsert: %d inserted, %d updated, %d skipped, %d errors",
        inserted, updated, skipped, errors,
    )
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "errors": errors}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/pipeline/test_dedup.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/uvo_pipeline/loaders/mongo.py tests/pipeline/test_dedup.py
git commit -m "feat: add pre-ingestion skip and ingested_docs registry to upsert_batch"
```

---

### Task 5: Propagate Skip Count in Orchestrator

**Files:**
- Modify: `src/uvo_pipeline/orchestrator.py`

- [ ] **Step 1: Write failing test**

Add to `tests/pipeline/test_dedup.py`:

```python
def test_pipeline_report_accumulates_skipped():
    """PipelineReport.notices_skipped must be settable and default to 0."""
    from datetime import datetime
    from uvo_pipeline.models import PipelineReport

    r = PipelineReport(run_id="x", mode="recent", started_at=datetime.utcnow())
    r.notices_skipped += 10
    assert r.notices_skipped == 10
```

- [ ] **Step 2: Run test to verify it passes** (already covered by Task 2 model change)

```bash
pytest tests/pipeline/test_dedup.py::test_pipeline_report_accumulates_skipped -v
```

Expected: PASS.

- [ ] **Step 3: Update orchestrator to propagate skipped count**

In `src/uvo_pipeline/orchestrator.py`, find the MongoDB upsert block (around line 273):

```python
            mongo_result = await upsert_batch(db, all_notices, batch_size=settings.batch_size)
            report.notices_inserted = mongo_result["inserted"]
            report.notices_updated = mongo_result["updated"]
            if mongo_result["errors"]:
                report.errors.append(f"MongoDB: {mongo_result['errors']} upsert errors")
```

Replace with:

```python
            mongo_result = await upsert_batch(db, all_notices, batch_size=settings.batch_size)
            report.notices_inserted = mongo_result["inserted"]
            report.notices_updated = mongo_result["updated"]
            report.notices_skipped = mongo_result["skipped"]
            if mongo_result["errors"]:
                report.errors.append(f"MongoDB: {mongo_result['errors']} upsert errors")
```

Also update the final log line (around line 298–300) to include skipped:

```python
        logger.info(
            "Pipeline run %s complete: %d inserted, %d updated, %d skipped",
            run_id, report.notices_inserted, report.notices_updated, report.notices_skipped,
        )
```

- [ ] **Step 4: Run all pipeline tests**

```bash
pytest tests/pipeline/ -v
```

Expected: All PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add src/uvo_pipeline/orchestrator.py
git commit -m "feat: propagate notices_skipped from upsert_batch into PipelineReport"
```

---

### Task 6: Cross-Source Dedup Pass 2 — Title-Slug Matching

**Files:**
- Modify: `src/uvo_pipeline/orchestrator.py`

- [ ] **Step 1: Write failing test**

Add to `tests/pipeline/test_dedup.py`:

```python
@pytest.mark.asyncio
async def test_cross_source_dedup_pass2_matches_by_title_slug(motor_db):
    """Pass 2 must match notices without ICO by title_slug + pub_date within 7 days."""
    from datetime import datetime
    from uvo_pipeline.loaders.mongo import ensure_indexes
    from uvo_pipeline.orchestrator import _run_cross_source_dedup

    await ensure_indexes(motor_db)

    run_id = "test-run-1"
    # Two notices from different sources, no ICO, same title, dates 3 days apart
    await motor_db.notices.insert_many([
        {
            "source": "uvo",
            "source_id": "U-100",
            "title": "Rekonštrukcia cesty",
            "title_slug": "rekonstrukcia-cesty",
            "procurer": {"ico": None, "name": "Obec Test", "name_slug": "obec-test"},
            "cpv_code": None,
            "publication_date": "2026-01-10",
            "pipeline_run_id": run_id,
            "canonical_id": None,
        },
        {
            "source": "vestnik",
            "source_id": "V-200",
            "title": "Rekonštrukcia cesty",
            "title_slug": "rekonstrukcia-cesty",
            "procurer": {"ico": None, "name": "Obec Test", "name_slug": "obec-test"},
            "cpv_code": None,
            "publication_date": "2026-01-13",
            "pipeline_run_id": run_id,
            "canonical_id": None,
        },
    ])

    match_count = await _run_cross_source_dedup(motor_db, run_id)
    assert match_count >= 1

    matched = await motor_db.notices.find(
        {"pipeline_run_id": run_id, "canonical_id": {"$ne": None}}
    ).to_list(length=None)
    assert len(matched) == 2
    assert matched[0]["canonical_id"] == matched[1]["canonical_id"]


@pytest.mark.asyncio
async def test_cross_source_dedup_pass2_no_match_when_dates_too_far(motor_db):
    """Pass 2 must NOT match notices with pub_date more than 7 days apart."""
    from uvo_pipeline.loaders.mongo import ensure_indexes
    from uvo_pipeline.orchestrator import _run_cross_source_dedup

    await ensure_indexes(motor_db)

    run_id = "test-run-2"
    await motor_db.notices.insert_many([
        {
            "source": "uvo",
            "source_id": "U-300",
            "title": "Stavebné práce",
            "title_slug": "stavebne-prace",
            "procurer": {"ico": None, "name": "Obec B", "name_slug": "obec-b"},
            "cpv_code": None,
            "publication_date": "2026-01-01",
            "pipeline_run_id": run_id,
            "canonical_id": None,
        },
        {
            "source": "vestnik",
            "source_id": "V-400",
            "title": "Stavebné práce",
            "title_slug": "stavebne-prace",
            "procurer": {"ico": None, "name": "Obec B", "name_slug": "obec-b"},
            "cpv_code": None,
            "publication_date": "2026-01-20",
            "pipeline_run_id": run_id,
            "canonical_id": None,
        },
    ])

    await _run_cross_source_dedup(motor_db, run_id)

    unmatched = await motor_db.notices.find(
        {"pipeline_run_id": run_id, "canonical_id": None}
    ).to_list(length=None)
    assert len(unmatched) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/pipeline/test_dedup.py::test_cross_source_dedup_pass2_matches_by_title_slug \
       tests/pipeline/test_dedup.py::test_cross_source_dedup_pass2_no_match_when_dates_too_far -v
```

Expected: FAIL — Pass 2 not yet implemented.

- [ ] **Step 3: Add `title_slug` to `CanonicalNotice` model**

In `src/uvo_pipeline/models.py`, add after `cpv_codes_additional`:

```python
    title_slug: str | None = None
```

- [ ] **Step 4: Add Pass 2 to `_run_cross_source_dedup`**

In `src/uvo_pipeline/orchestrator.py`, replace the entire `_run_cross_source_dedup` function:

```python
async def _run_cross_source_dedup(db: AsyncIOMotorDatabase, run_id: str) -> int:
    """
    Find notices from different sources that likely refer to the same real-world event.

    Pass 1: Match by (procurer.ico, cpv_code) across sources.
    Pass 2: For notices without ICO, match by (title_slug, publication_date ±7 days) across sources.

    For each group of matches:
    1. Assign a shared canonical_id (MongoDB _id of oldest notice as string)
    2. Update all notices with that canonical_id
    3. Write a record to cross_source_matches collection

    Returns total number of cross-source match groups found.
    """
    match_count = 0

    # --- Pass 1: procurer.ico + cpv_code ---
    pipeline_pass1 = [
        {"$match": {
            "procurer.ico": {"$ne": None, "$exists": True},
            "cpv_code": {"$ne": None, "$exists": True},
            "pipeline_run_id": run_id,
        }},
        {"$group": {
            "_id": {"procurer_ico": "$procurer.ico", "cpv_code": "$cpv_code"},
            "notices": {"$push": {"id": "$_id", "source": "$source", "pub_date": "$publication_date"}},
            "sources": {"$addToSet": "$source"},
        }},
        {"$match": {"sources.1": {"$exists": True}}},
    ]

    groups = await db.notices.aggregate(pipeline_pass1).to_list(length=None)

    for group in groups:
        notices_in_group = group["notices"]
        notices_in_group.sort(key=lambda x: x.get("pub_date") or "")
        canonical_id = str(notices_in_group[0]["id"])
        notice_ids = [str(n["id"]) for n in notices_in_group]

        await db.notices.update_many(
            {"_id": {"$in": [ObjectId(nid) for nid in notice_ids]}},
            {"$set": {"canonical_id": canonical_id}},
        )
        await db.cross_source_matches.update_one(
            {"canonical_id": canonical_id},
            {"$set": {
                "canonical_id": canonical_id,
                "notice_ids": notice_ids,
                "sources": group["sources"],
                "procurer_ico": group["_id"]["procurer_ico"],
                "cpv_code": group["_id"]["cpv_code"],
                "match_type": "ico_cpv",
            }},
            upsert=True,
        )
        match_count += 1

    # --- Pass 2: title_slug + publication_date ±7 days (for notices without ICO) ---
    # Fetch ICO-less notices from this run that have a title_slug and no canonical_id yet
    ico_less = await db.notices.find({
        "pipeline_run_id": run_id,
        "title_slug": {"$ne": None, "$exists": True},
        "canonical_id": None,
        "$or": [
            {"procurer.ico": None},
            {"procurer.ico": {"$exists": False}},
        ],
    }).to_list(length=None)

    # Group by title_slug
    from collections import defaultdict
    by_slug: dict[str, list] = defaultdict(list)
    for n in ico_less:
        slug = n.get("title_slug")
        if slug:
            by_slug[slug].append(n)

    for slug, slug_notices in by_slug.items():
        if len(slug_notices) < 2:
            continue

        # Find clusters within ±7 days of each other, across different sources
        # Simple greedy: sort by date, merge notices within 7-day window
        slug_notices.sort(key=lambda x: x.get("publication_date") or "")

        processed: set[str] = set()
        for i, anchor in enumerate(slug_notices):
            if str(anchor["_id"]) in processed:
                continue

            anchor_date_str = anchor.get("publication_date")
            if not anchor_date_str:
                continue

            try:
                from datetime import date as date_type
                anchor_date = date_type.fromisoformat(str(anchor_date_str))
            except (ValueError, TypeError):
                continue

            cluster = [anchor]
            cluster_sources = {anchor["source"]}

            for other in slug_notices[i + 1:]:
                if str(other["_id"]) in processed:
                    continue
                if other["source"] == anchor["source"]:
                    continue
                other_date_str = other.get("publication_date")
                if not other_date_str:
                    continue
                try:
                    other_date = date_type.fromisoformat(str(other_date_str))
                except (ValueError, TypeError):
                    continue
                if abs((other_date - anchor_date).days) <= 7:
                    cluster.append(other)
                    cluster_sources.add(other["source"])

            if len(cluster_sources) < 2:
                continue  # Same source duplicates — not cross-source

            cluster.sort(key=lambda x: x.get("publication_date") or "")
            canonical_id = str(cluster[0]["_id"])
            notice_ids = [str(n["_id"]) for n in cluster]

            await db.notices.update_many(
                {"_id": {"$in": [ObjectId(nid) for nid in notice_ids]}},
                {"$set": {"canonical_id": canonical_id}},
            )
            await db.cross_source_matches.update_one(
                {"canonical_id": canonical_id},
                {"$set": {
                    "canonical_id": canonical_id,
                    "notice_ids": notice_ids,
                    "sources": list(cluster_sources),
                    "title_slug": slug,
                    "match_type": "title_slug_date",
                }},
                upsert=True,
            )
            for n in cluster:
                processed.add(str(n["_id"]))
            match_count += 1

    return match_count
```

- [ ] **Step 5: Run all dedup tests**

```bash
pytest tests/pipeline/test_dedup.py -v
```

Expected: All PASS.

- [ ] **Step 6: Run full pipeline test suite**

```bash
pytest tests/pipeline/ -v
```

Expected: All PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/uvo_pipeline/models.py src/uvo_pipeline/orchestrator.py tests/pipeline/test_dedup.py
git commit -m "feat: add Pass 2 cross-source dedup by title_slug and publication_date"
```

---

### Task 7: Compute Hash in Transformers

**Files:**
- Modify: `src/uvo_pipeline/orchestrator.py`

The hash must be set before `upsert_batch` is called. The cleanest place is in the orchestrator, right before the batch write.

- [ ] **Step 1: Write failing test**

Add to `tests/pipeline/test_dedup.py`:

```python
def test_notice_hash_set_before_upsert():
    """Notices must have content_hash set before reaching upsert_batch."""
    from uvo_pipeline.utils.hashing import compute_notice_hash

    n = _make_notice()
    assert n.content_hash is None  # default — not set by model

    n.content_hash = compute_notice_hash(n)
    assert n.content_hash is not None
    assert n.content_hash.startswith("sha256:")
```

- [ ] **Step 2: Run test to verify it passes** (already passes — just documents the contract)

```bash
pytest tests/pipeline/test_dedup.py::test_notice_hash_set_before_upsert -v
```

Expected: PASS.

- [ ] **Step 3: Add hash computation in orchestrator before `upsert_batch`**

In `src/uvo_pipeline/orchestrator.py`, add the import near the top of the `run` function (inside the try block, before the upsert call):

```python
        if all_notices:
            # Compute content hashes before writing
            from uvo_pipeline.utils.hashing import compute_notice_hash
            for notice in all_notices:
                notice.content_hash = compute_notice_hash(notice)

            # Write to MongoDB
            mongo_result = await upsert_batch(db, all_notices, batch_size=settings.batch_size)
```

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/pipeline/ -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/uvo_pipeline/orchestrator.py tests/pipeline/test_dedup.py
git commit -m "feat: compute content_hash for all notices in orchestrator before upsert"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| `ingested_docs` collection with schema | Task 3 (indexes) + Task 4 (writes) |
| `content_hash` on `CanonicalNotice` | Task 1 (hashing.py) + Task 2 (model field) |
| Pre-ingestion skip (unchanged docs) | Task 4 |
| Skip count in `PipelineReport` | Task 2 (model) + Task 5 (orchestrator) |
| `ingested_docs` indexes | Task 3 |
| Cross-source dedup Pass 2 (title_slug ±7d) | Task 6 |
| `title_slug` field on `CanonicalNotice` | Task 6 Step 3 |
| Hash computed before upsert | Task 7 |

All spec requirements covered. No gaps found.
