# UVO Search — Data Pipeline

## Overview

Seven long-lived microservices ingest Slovak public procurement data from five sources (UVO Vestník, CRZ, ITMS, TED, NKOD) into MongoDB and Neo4j via Redis Streams. Each service owns its extraction cadence, rate-limit budget, and failure domain. The legacy one-shot `pipeline` service is preserved for ad-hoc historical backfills.

**Status**: Microservices architecture (source-per-service) implemented as of 2026-04-27. See the detailed design spec at [docs/superpowers/specs/2026-04-27-source-microservices-design.md](superpowers/specs/2026-04-27-source-microservices-design.md).

---

## Architecture

```
[NKOD / data.gov.sk]   [UVO Vestník XML]    [Ekosystem CRZ]    [ITMS]    [TED EU API]
       │                      │                    │              │          │
       └──────────────────────┼────────────────────┼──────────────┼──────────┘
                              │
                   ┌──────────┴──────────┐
                   │ extractors/         │
                   │ (4 daemons)         │
                   └────────┬────────────┘
                            │
                   ┌────────▼──────────┐
                   │ Redis Streams     │
                   │ notices:vestnik   │
                   │ notices:crz       │
                   │ notices:ted       │
                   │ notices:itms      │
                   └────────┬──────────┘
                            │ XREADGROUP
                   ┌────────▼──────────┐
                   │ ingestor          │
                   │ (transforms +     │
                   │  upserts)         │
                   └────────┬──────────┘
                            │ PUBLISH notices:written
                   ┌────────▼──────────┐
                   │ Redis pub/sub      │
                   │ (event trigger)    │
                   └────────┬──────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼─────┐        ┌────▼──────┐      ┌────▼──────┐
   │ MongoDB   │        │ Neo4j     │      │ dedup-    │
   │ notices   │        │ graph     │      │ worker    │
   │ procurers │        │           │      │ (debounce │
   │ suppliers │        │           │      │  5s)      │
   │ cross_src │        │           │      └───────────┘
   │ pipeline_ │        │           │
   │ state     │        │           │
   └───────────┘        └───────────┘
        │                   │
        └───────────┬───────┘
                    │
           MCP Server (port 8000)
           src/uvo_mcp/
```

**New packages & modules** (`uvo_pipeline` shared lib + `uvo_workers` daemon entrypoints):
- `src/uvo_pipeline/` (shared, no rename):
  - `redis_client.py` — async Redis factory
  - `streams.py` — XADD, XREADGROUP, XACK helpers
  - `pubsub.py` — PUBLISH, SUBSCRIBE helpers
  - `locks.py` — distributed lock CAS
  - `cache/` (memory.py, redis.py) — ITMS cache backends
  - `dedup.py` — cross-source dedup logic
  - `extractors/` — unchanged (+ `cache_backend` param for ITMS)
- `src/uvo_workers/` (new package):
  - `runner.py` — daemon loop, signal handling, /health, lock acquisition
  - `vestnik.py`, `crz.py`, `ted.py`, `itms.py` — per-source extractors
  - `ingestor.py` — streams consumer
  - `dedup.py` — dedup subscriber

---

## Data Sources

| Source | Type | Auth | Update Frequency | Coverage |
|---|---|---|---|---|
| UVO Vestník (XML) | Anonymous XML download | None | Per UVO publication schedule | 2016–present |
| UVO Vestník via NKOD | DCAT/SPARQL catalog | None | Daily (working days) | 2016–present |
| Ekosystem CRZ | REST API | Optional token | Continuous | 2011–present |
| ITMS | Open data / REST | None | Per ITMS publication schedule | EU structural funds |
| TED EU API | REST API | None | Daily | All above-threshold |
| NKOD catalog | CKAN / DCAT | None | On publisher update | Catalog metadata |

---

## Microservices Operation

### Extractors (vestnik, crz, ted, itms)

Each runs on its own interval (config via `<SOURCE>_INTERVAL_SECONDS` in `.env`):

```bash
# Default intervals:
VESTNIK_INTERVAL_SECONDS=3600  # 1 hour
CRZ_INTERVAL_SECONDS=3600      # 1 hour
TED_INTERVAL_SECONDS=21600     # 6 hours
ITMS_INTERVAL_SECONDS=3600     # 1 hour

# Health check (per service):
curl http://localhost:8091/health  # vestnik
curl http://localhost:8092/health  # crz
curl http://localhost:8093/health  # ted
curl http://localhost:8094/health  # itms
```

Per-cycle behavior:
1. Acquire distributed lock `extractor:lock:<source>` (TTL = 2×interval)
2. Iterate source API, buffer `CanonicalNotice` objects
3. Every 500 items (configurable `BATCH_SIZE`): `XADD notices:<source> MAXLEN ~ 100000 ...`
4. After API loop: flush remainder + update checkpoint in Mongo `pipeline_state`
5. Release lock, sleep until next interval

### Ingestor

Continuous daemon reading all 4 Redis Streams:

```bash
# Health check:
curl http://localhost:8095/health

# Behavior:
XREADGROUP GROUP ingestor <instance-id> COUNT <INGESTOR_BATCH_SIZE>
           BLOCK 5000 STREAMS notices:vestnik notices:crz notices:ted notices:itms > > > >
# → decode payloads, upsert Mongo+Neo4j
# → on success: XACK + PUBLISH notices:written
# → on failure: skip XACK (re-delivers next read)
```

### Dedup-worker

Event-driven with fallback poll:

```bash
# Health check:
curl http://localhost:8096/health

# Behavior:
SUBSCRIBE notices:written
# Debounce 5 seconds (DEDUP_DEBOUNCE_SECONDS)
# Fallback poll every 1 hour (DEDUP_INTERVAL_SECONDS) if no events arrive
# Run cross_source_dedup filtered on canonical_id IS NULL + ingested_at >= now - 30 days
```

### Legacy: One-shot pipeline (ad-hoc backfill only)

```bash
# Historical backfill (full rebuild from 2014)
docker compose run --rm pipeline run --mode historical

# Recent backfill (last 365 days)
docker compose run --rm pipeline run --mode recent

# Dry run (validation only)
docker compose run --rm pipeline run --mode recent --dry-run
```

The legacy `pipeline` service is kept in `docker-compose.yml` for backwards compatibility; new continuous ingestion runs via the 6 microservices above.

---

## Common Data Schema

All sources normalize to `CanonicalNotice` before any DB write. See `src/uvo_pipeline/models.py`.

**Deduplication keys per source:**

| Source | Primary dedup key | Notes |
|---|---|---|
| `vestnik` | `(source="vestnik", source_id=notice_id)` | notice_id from XML `cbc:ID` |
| `crz` | `(source="crz", source_id=str(id))` | Ekosystem contract ID |
| `itms` | `(source="itms", source_id=str(id))` | ITMS project/contract ID |
| `ted` | `(source="ted", source_id=ND_OJ)` | TED official journal number |

**Cross-source deduplication:** After each pipeline run, notices with matching `(procurer_ico, cpv_code)` from different sources are linked via a shared `canonical_id` field. Links are stored in the `cross_source_matches` collection.

---

## MongoDB Collections

**Database:** `uvo_search`

| Collection | Dedup key | Key indexes |
|---|---|---|
| `notices` | `(source, source_id)` unique | `publication_date desc`, `procurer.ico`, `cpv_code`, `awards.supplier.ico`, text on `title`+`description` |
| `procurers` | `ico` unique (sparse) + `name_slug` unique | text on `name` |
| `suppliers` | `ico` unique (sparse) + `name_slug` unique | text on `name` |
| `cross_source_matches` | `canonical_id` | `notice_ids` array |
| `pipeline_state` | `source` unique | — |
| `ckan_packages` | `package_id` unique | `last_modified desc` |

---

## Neo4j Graph Model

### Nodes

| Label | Key property | Description |
|---|---|---|
| `Procurer` | `ico` | Contracting authority |
| `Supplier` | `ico` | Awarded contractor |
| `Notice` | `(source, source_id)` | Procurement notice/award |
| `CPVCode` | `code` | Common Procurement Vocabulary code |
| `Contract` | `crz_contract_id` | CRZ contract record |

### Relationships

```cypher
(:Procurer)-[:ISSUED {publication_date}]->(:Notice)
(:Notice)-[:AWARDED_TO {value, currency, award_date}]->(:Supplier)
(:Notice)-[:CLASSIFIED_BY]->(:CPVCode)
(:Notice)-[:SAME_AS {confidence}]->(:Notice)
(:Notice)-[:RESULTED_IN]->(:Contract)
```

### Example queries

Find top suppliers for a contracting authority:
```cypher
MATCH (:Procurer {ico: "12345678"})-[:ISSUED]->(n:Notice)-[r:AWARDED_TO]->(s:Supplier)
RETURN s.name, count(n) AS contracts, sum(r.value) AS total
ORDER BY total DESC LIMIT 10
```

Find organisations connected through shared contracts:
```cypher
MATCH (start {ico: "12345678"})-[*1..2]-(related)
WHERE (related:Procurer OR related:Supplier)
RETURN DISTINCT related.name, related.ico, labels(related)[0]
```

---

## Running the Pipeline

### Full stack (microservices + storage)

```bash
# Start all services
docker compose up -d

# Watch logs (all services)
docker compose logs -f

# Stop all services
docker compose down
```

### Individual service operations

```bash
# Build images
docker compose build redis extractor-vestnik extractor-crz extractor-ted extractor-itms ingestor dedup-worker

# Start new stack (without legacy pipeline, for cutover):
docker compose up -d redis extractor-vestnik extractor-crz extractor-ted extractor-itms ingestor dedup-worker

# Stop microservices (keep legacy pipeline if needed)
docker compose stop extractor-vestnik extractor-crz extractor-ted extractor-itms ingestor dedup-worker

# Watch stream backlog (should drain to ~0)
docker compose exec redis redis-cli XLEN notices:vestnik
docker compose exec redis redis-cli XLEN notices:crz
docker compose exec redis redis-cli XLEN notices:ted
docker compose exec redis redis-cli XLEN notices:itms

# Check pipeline state (per-source checkpoints)
docker compose exec mongo mongosh -u uvo -p $MONGO_PASSWORD uvo_search \
  --eval "db.pipeline_state.find().pretty()"

# Check notices & dedup results
docker compose exec mongo mongosh -u uvo -p $MONGO_PASSWORD uvo_search \
  --eval "db.notices.countDocuments({})"
docker compose exec mongo mongosh -u uvo -p $MONGO_PASSWORD uvo_search \
  --eval "db.cross_source_matches.countDocuments({})"
```

### Health & monitoring

```bash
# Per-service /health endpoints (JSON snapshots)
curl http://localhost:8091/health  # extractor-vestnik
curl http://localhost:8092/health  # extractor-crz
curl http://localhost:8093/health  # extractor-ted
curl http://localhost:8094/health  # extractor-itms
curl http://localhost:8095/health  # ingestor
curl http://localhost:8096/health  # dedup-worker
```

### Storage inspection

```bash
# Open MongoDB shell
docker compose exec mongo mongosh -u uvo -p $MONGO_PASSWORD uvo_search

# Open Neo4j Browser
# http://localhost:7474  (user: neo4j, password from NEO4J_PASSWORD env var)

# Open Redis CLI
docker compose exec redis redis-cli
```

---

## Checkpoints & State

Per-source checkpoints are stored in the `pipeline_state` MongoDB collection (one document per `source`):

```javascript
// In mongosh:
db.pipeline_state.find()  // all checkpoints

// Sample document:
{
  "_id": ObjectId("..."),
  "source": "vestnik",
  "last_run_at": ISODate("2026-04-27T12:34:56Z"),
  "last_modified": "2026-04-27",  // Vestník last_modified date
  "itms_min_id": 0  // ITMS-specific: min_id for next fetch
}
```

Each extractor updates its checkpoint after successfully writing to the stream. On restart, the extractor resumes from the checkpoint date (or start of time if none exists).

**Reset a source checkpoint** (force full re-fetch from start of time):

```javascript
// In mongosh:
db.pipeline_state.deleteOne({source: "vestnik"})
// Next cycle of extractor-vestnik will start from day 1
```

**ITMS special handling**: The `itms_min_id` field tracks progress through ITMS pagination. Updated after each successful stream flush.

---

## Environment Variables

All configuration lives in `.env` (interpolated by Docker Compose):

```bash
# Storage
MONGO_PASSWORD=changeme
NEO4J_PASSWORD=changeme

# Redis (new — required for microservices)
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=

# Extractor intervals (seconds)
VESTNIK_INTERVAL_SECONDS=3600     # 1 hour
CRZ_INTERVAL_SECONDS=3600         # 1 hour
TED_INTERVAL_SECONDS=21600        # 6 hours
ITMS_INTERVAL_SECONDS=3600        # 1 hour

# Extractor modes (all default to "recent")
VESTNIK_MODE=recent
CRZ_MODE=recent
TED_MODE=recent
ITMS_MODE=recent

# Cross-source deduplication (event-driven + fallback poll)
DEDUP_INTERVAL_SECONDS=3600       # 1 hour fallback poll
DEDUP_DEBOUNCE_SECONDS=5          # coalesce events within 5s
DEDUP_WINDOW_DAYS=30              # only dedup notices ingested in last 30 days

# ITMS cache backend (Redis by default in production)
ITMS_CACHE_BACKEND=redis          # or "memory" for tests
ITMS_CACHE_TTL_SECONDS=604800     # 7 days

# Ingestor batching
INGESTOR_BATCH_SIZE=100           # messages per XREADGROUP call
STREAM_MAXLEN_APPROX=100000       # approximate max entries per stream

# Legacy pipeline (one-shot backfill mode)
HISTORICAL_FROM_YEAR=2014         # used by `pipeline run --mode historical`
RECENT_DAYS=365                   # used by `pipeline run --mode recent`
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Extractors keep skipping cycles | Lock conflict (another instance running) | Kill the competing container, wait for lock to expire (2× interval) |
| Stream backlog grows (`XLEN` doesn't return to ~0) | Ingestor down or stuck | Check `docker compose logs ingestor`, restart with `docker compose restart ingestor` |
| `429 Too Many Requests` from source API | Rate limit exceeded | Increase interval in `.env` or lower `BATCH_SIZE` |
| Ingestor fails to write to Mongo | Connection down or permission error | Check `docker compose logs ingestor`, verify `MONGO_PASSWORD`, restart stack |
| Dedup-worker never runs | No `notices:written` events (ingestor not publishing) | Check `docker compose logs ingestor` and `docker compose logs dedup-worker` |
| Redis connection refused | Redis not running or wrong URI | Verify `REDIS_URL` in `.env`, run `docker compose up redis` |
| ITMS extractor re-fetches everything on restart | Cache backend is `memory` (in-process only) | Set `ITMS_CACHE_BACKEND=redis` for persistent cache across restarts |
| Neo4j OOM | Heap too small | Set `NEO4J_server_memory_heap_max__size: 2g` in `docker-compose.yml` |

---

## Adding a New Data Source

1. Add extractor: `src/uvo_pipeline/extractors/<source>.py` — async generator yielding raw dicts
2. Add transformer: `src/uvo_pipeline/transformers/<source>.py` — `transform_<entity>(raw) -> CanonicalNotice`
3. For microservices: Create daemon entry in `src/uvo_workers/<source>.py` (inherits from `runner.py`)
   - Implement extraction loop, stream publishing, checkpoint update
   - Expose via `uv run python -m uvo_workers.<source>`
   - Add to `docker-compose.yml` service block
4. For legacy pipeline: Add extraction block to `src/uvo_pipeline/orchestrator.py::run()`
5. Add tests: `tests/pipeline/extractors/test_<source>.py`, `tests/pipeline/transformers/test_<source>.py`
6. Add checkpoint key to `pipeline_state` MongoDB if the source needs incremental tracking
