# Deduplication & Ingestion Registry — Design Spec

**Date:** 2026-04-11  
**Status:** Approved  
**Scope:** UVO pipeline — pre-ingestion skip, ingestion audit trail, cross-source dedup enhancement

---

## Problem

The UVO pipeline currently:
- Re-processes and re-writes already-seen documents on every run (slow runs, unnecessary DB write load)
- Has no durable audit trail of what was ingested, when, and from which source
- Cross-source dedup only matches on `(procurer.ico, cpv_code)` — misses same-event notices where ICO is absent

---

## Solution: Option A — Ingestion Registry Collection

A dedicated `ingested_docs` collection acts as a fast lookup set + audit log. Pre-ingestion check skips unchanged docs. Content hash enables change detection. Cross-source dedup gets a second pass for ICO-less notices.

---

## Architecture

### 1. `ingested_docs` Collection

Lightweight registry — one doc per ingested notice, no full body stored.

**Schema:**
```json
{
  "source": "uvo",
  "source_id": "12345",
  "content_hash": "sha256:abcdef...",
  "ingested_at": "2026-04-11T10:00:00Z",
  "last_seen_at": "2026-04-11T10:00:00Z",
  "pipeline_run_id": "uuid",
  "skipped_count": 0
}
```

**Indexes:**
- `UNIQUE (source, source_id)` — primary lookup key
- `(pipeline_run_id)` — query by run
- `(source, ingested_at desc)` — audit queries by source + time
- `(ingested_at desc)` — global timeline queries

### 2. Content Hash on `CanonicalNotice`

Add `content_hash: str | None = None` field to `CanonicalNotice` in `models.py`.

**New module:** `src/uvo_pipeline/utils/hashing.py`

Hash inputs (stable subset, order-fixed):
```
sha256("|".join([
    notice.source,
    notice.source_id,
    notice.title or "",
    notice.procurer.ico if notice.procurer else "",
    notice.cpv_code or "",
    str(notice.publication_date or ""),
    str(notice.estimated_value or ""),
]))
```

Hash is computed and set on `CanonicalNotice` before the batch upsert, not in the transformer.

### 3. Pre-Ingestion Skip in `upsert_batch`

**Location:** `src/uvo_pipeline/loaders/mongo.py` — `upsert_batch()`

**Flow:**
1. Compute hashes for all notices in batch (if not already set).
2. Bulk-fetch `ingested_docs` for all `(source, source_id)` pairs in the batch — single DB query per batch.
3. For each notice:
   - **New** (`source_id` not in registry) → upsert notice, insert registry entry, count as `inserted`
   - **Unchanged** (hash matches registry) → skip upsert, update `last_seen_at` + increment `skipped_count` in registry, count as `skipped`
   - **Changed** (hash differs) → upsert notice, update registry hash + `last_seen_at`, count as `updated`
4. Return `{"inserted", "updated", "skipped", "errors"}`.

### 4. Cross-Source Dedup Enhancement

**Location:** `src/uvo_pipeline/orchestrator.py` — `_run_cross_source_dedup()`

**Pass 1 (existing):** Match on `(procurer.ico, cpv_code)` across sources — unchanged.

**Pass 2 (new):** For notices where `procurer.ico` is null, match on `(title_slug, publication_date)` within ±7 days across different sources. `title_slug` is derived from the existing `name_slug` pattern (lowercase, stripped, hyphenated). This catches UVO/Vestník duplicates where ICO is absent.

Both passes assign `canonical_id` and write to `cross_source_matches` — same mechanism as today.

### 5. `PipelineReport` Extension

Add `notices_skipped: int = 0` to `PipelineReport` in `models.py`.

Orchestrator propagates skip count from `upsert_batch` result into report. Log line per source: `"UVO: 1200 extracted, 950 skipped (unchanged), 250 upserted"`.

---

## Data Flow

```
Extract → Transform → compute_hash() → upsert_batch()
                                            ↓
                                 bulk_fetch ingested_docs
                                            ↓
                              ┌─────────────┴──────────────┐
                           new/changed                  unchanged
                              ↓                             ↓
                      upsert notices               update last_seen_at
                      update registry              increment skipped_count
                              ↓
                   _run_cross_source_dedup()
                   Pass 1: (ico, cpv_code)
                   Pass 2: (title_slug, pub_date ±7d)
```

---

## Files Changed

| File | Change |
|------|--------|
| `src/uvo_pipeline/models.py` | Add `content_hash` to `CanonicalNotice`; add `notices_skipped` to `PipelineReport` |
| `src/uvo_pipeline/utils/hashing.py` | New — `compute_notice_hash(notice) -> str` |
| `src/uvo_pipeline/loaders/mongo.py` | `ensure_indexes`: add `ingested_docs` indexes; `upsert_batch`: pre-ingestion check + registry upsert |
| `src/uvo_pipeline/orchestrator.py` | Pass hashes to batch; propagate `skipped` to report; add Pass 2 to `_run_cross_source_dedup` |
| `tests/pipeline/test_dedup.py` | New — unit tests for hash stability, skip logic, Pass 2 cross-source match |

---

## Out of Scope

- Deleting duplicate notices from `notices` collection (cross-source matches are links, not deletions — unchanged)
- Bloom filter / in-memory hash set (Option B — deferred, corpus too small to justify now)
- Backfilling `ingested_docs` for historical notices already in DB (can be done as a one-off migration script later if needed)
