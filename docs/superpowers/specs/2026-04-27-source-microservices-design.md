# Source-per-service ingestion architecture

**Status:** Implemented (2026-04-27); cutover pending operator action
**Date:** 2026-04-27
**Replaces:** the single `pipeline` one-shot container

## Problem

Today every source (Vestník, CRZ, TED, ITMS) runs sequentially inside one
`pipeline` container. Slow sources block fast ones (CRZ runs ~2 hours; the
others are minutes), a single rate-limit or 5xx halts the whole run, and
operators cannot iterate on one source without restarting all of them.

Cross-source dedup is also coupled to one pipeline run id — it has no path to
trigger when a single source writes new data outside that run.

## Goal

Run each source as an independent, long-running microservice. Each service
owns its cadence, its rate-limit budget, its checkpoint, and its failure
domain. Decouple extraction from persistence by routing all writes through
Redis Streams. Trigger cross-source dedup on event rather than on schedule.

## Non-goals

- Horizontal scaling of any service (one container per role).
- Prometheus / Grafana metrics — `/health` JSON per service is enough for now.
- Renaming the existing `uvo_pipeline` package.
- A direct UVO extractor — uvo.gov.sk has no public API; Vestník NKOD already
  covers UVO via the publisher-URI filter.
- A queue/broker (RabbitMQ, NATS). Redis Streams covers the use case.

## Topology

Seven services after migration:

| Service              | Image                  | Role                                                         | Cadence              |
| -------------------- | ---------------------- | ------------------------------------------------------------ | -------------------- |
| `redis`              | `redis:7-alpine`       | streams, pub-sub, ITMS cache, distributed locks              | always-on            |
| `extractor-vestnik`  | `uvo-search-pipeline`  | extract → `XADD notices:vestnik`                             | 1 h                  |
| `extractor-crz`      | `uvo-search-pipeline`  | extract → `XADD notices:crz`                                 | 1 h                  |
| `extractor-ted`      | `uvo-search-pipeline`  | extract → `XADD notices:ted`                                 | 6 h                  |
| `extractor-itms`     | `uvo-search-pipeline`  | extract (Redis-cached subject/supplier) → `XADD notices:itms`| 1 h                  |
| `ingestor`           | `uvo-search-pipeline`  | `XREADGROUP` 4 streams → upsert Mongo+Neo4j → `XACK` → `PUBLISH notices:written` | continuous |
| `dedup-worker`       | `uvo-search-pipeline`  | `SUBSCRIBE notices:written` → debounce → cross-source dedup  | event-driven, 1 h fallback poll |

All seven application services share the existing `uvo-search-pipeline`
image — only `command:` differs. UVO is intentionally absent.

```
            ┌─────────────────────────┐
            │         redis           │  streams + pub-sub + cache + locks
            └─────────────────────────┘
                 ▲                  ▲                 ▲
                 │ XADD             │ pub             │ GET / SETEX
                 │                  │                 │
   ┌────────────────────┐   ┌─────────────┐   ┌────────────────┐
   │ extractor-vestnik  │   │  ingestor   │   │ extractor-itms │
   │ extractor-crz      │──▶│ XREADGROUP  │──▶│ Mongo + Neo4j  │
   │ extractor-ted      │   │ upsert      │   └────────────────┘
   │ extractor-itms     │   │ PUBLISH     │
   └────────────────────┘   └─────────────┘
                                    │ notices:written
                                    ▼
                             ┌──────────────┐
                             │ dedup-worker │
                             └──────────────┘
```

## Data flow per extraction cycle

1. Daemon loop tick fires (per `<SOURCE>_INTERVAL_SECONDS`).
2. Acquire distributed lock `extractor:lock:<source>` (SET NX EX `2*interval`).
   On fail, log + skip cycle.
3. Open HTTP client(s), iterate the source API.
4. Buffer transformed `CanonicalNotice` objects in memory. Every
   `BATCH_SIZE` items (default 500):
   `XADD notices:<source> MAXLEN ~ <STREAM_MAXLEN_APPROX> *
       payload <json> hash <content_hash> run <run_id>`
   then clear buffer.
5. After the API loop, flush remainder via the same `XADD`.
6. Update per-source checkpoint in Mongo (`pipeline_state`); for ITMS this is
   the post-flush `min_id` so a crash only loses the partial buffer.
7. Release the lock. Sleep `<SOURCE>_INTERVAL_SECONDS`.

The ingestor runs an independent loop:

1. `XREADGROUP GROUP ingestor <instance-id> COUNT <INGESTOR_BATCH_SIZE>
       BLOCK 5000 STREAMS notices:vestnik notices:crz notices:ted notices:itms
       > > > >`
2. Decode payloads → list of `CanonicalNotice`.
3. Call existing `upsert_batch(db, notices)` and `merge_notice_batch(neo4j, notices)`.
   Existing content-hash skip logic preserved end-to-end.
4. On Mongo success: `XACK` each delivered id; on failure: leave unacked so
   the next read re-delivers.
5. After successful batch: `PUBLISH notices:written {"source": ..., "count": ...}`.

Dedup-worker:

1. `SUBSCRIBE notices:written`.
2. Collect events for `DEDUP_DEBOUNCE_SECONDS` (default 5). Coalesce into one
   trigger.
3. Run `cross_source_dedup` filtered on
   `canonical_id is null AND ingested_at >= now - DEDUP_WINDOW_DAYS` (default 30).
   Idempotent — already-linked notices are filtered out by the canonical_id
   predicate.
4. Fallback poll: if no event arrives for `DEDUP_INTERVAL_SECONDS` (default
   3600), trigger anyway — covers the case where Redis pub-sub drops a message
   while the worker is restarting.

## Code layout

```
src/
  uvo_pipeline/                          # shared library — no rename
    extractors/
      itms.py                            # + cache_backend parameter
      vestnik_nkod.py / crz.py / ted.py  # unchanged
    transformers/, loaders/, models.py, config.py
    dedup.py                             # NEW — moved out of orchestrator.py
    redis_client.py                      # NEW — async redis factory
    streams.py                           # NEW — XADD / XREADGROUP / XACK helpers
    pubsub.py                            # NEW — PUBLISH / SUBSCRIBE helpers
    locks.py                             # NEW — Redis lock CAS helpers
    cache/
      __init__.py
      memory.py                          # default in-process dict (tests)
      redis.py                           # Redis-backed (prod)
  uvo_workers/                           # NEW package — daemon entrypoints
    runner.py                            # daemon loop + signal handling + /health + lock
    vestnik.py / crz.py / ted.py / itms.py
    ingestor.py
    dedup.py
```

`uvo_pipeline.orchestrator.run()` stays usable as `python -m uvo_pipeline ...`
for ad-hoc backfills, but is no longer wired into Compose.

## Configuration

All knobs in `.env` (Compose interpolates with defaults):

```
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=

VESTNIK_INTERVAL_SECONDS=3600
CRZ_INTERVAL_SECONDS=3600
TED_INTERVAL_SECONDS=21600
ITMS_INTERVAL_SECONDS=3600

VESTNIK_MODE=recent
CRZ_MODE=recent
TED_MODE=recent
ITMS_MODE=recent

DEDUP_INTERVAL_SECONDS=3600
DEDUP_DEBOUNCE_SECONDS=5
DEDUP_WINDOW_DAYS=30

ITMS_CACHE_BACKEND=redis
ITMS_CACHE_TTL_SECONDS=604800

INGESTOR_BATCH_SIZE=100
STREAM_MAXLEN_APPROX=100000
```

`docker-compose.yml` interpolates with `${VESTNIK_INTERVAL_SECONDS:-3600}`,
etc. — `.env` is the source of truth, code defaults are the fallback.

## Reliability and failure modes

- **Redis unreachable on startup**: extractors, ingestor, dedup-worker exit
  non-zero. `restart: unless-stopped` cycles them. `/health` returns 503 once
  running but disconnected.
- **Ingestor down for hours**: streams grow up to `STREAM_MAXLEN_APPROX`
  entries (~100k each at default — roughly 50 MB per source). Extractors keep
  running because `XADD` doesn't require a consumer. On recovery, the consumer
  group cursor resumes where it left off; nothing acked is lost. If MAXLEN
  trims unacked entries (only under heavy backlog), the next extractor cycle
  re-emits them and the content-hash check makes the re-upsert a no-op.
- **One extractor crashes**: peers and ingestor unaffected. The lock auto-
  expires in `2*interval`, so the next cycle proceeds normally even if the
  crashed instance never released cleanly.
- **Mongo or Neo4j write fails inside ingestor**: do not `XACK`. Stream
  re-delivers on the next read. Existing upsert is idempotent.
- **Dedup pub-sub message lost**: the `DEDUP_INTERVAL_SECONDS` poll fallback
  catches up within the hour.
- **Two extractor instances of the same source (operator error)**: only one
  acquires the lock per cycle; the other logs and skips. No double writes.

## ITMS cache

The current ITMS extractor maintains `subject_cache` and `supplier_cache` as
in-process dicts; they die on restart, forcing re-fetch of every subject and
supplier id every cycle.

Introduce a small interface:

```python
class CacheBackend(Protocol):
    async def get(self, key: str) -> dict | None: ...
    async def set(self, key: str, value: dict, *, ttl_seconds: int) -> None: ...
```

Two implementations:

- `MemoryCache` — current behavior, used by tests.
- `RedisCache` — keys `itms:subject:<id>`, `itms:supplier:<id>`,
  TTL `ITMS_CACHE_TTL_SECONDS` (7 days).

`fetch_procurements` accepts a `cache_backend` argument; default stays
`MemoryCache` so the existing extractor tests need no Redis.

## Distributed lock

```python
# acquire
ok = await redis.set(f"extractor:lock:{source}", instance_id,
                     nx=True, ex=2 * interval_seconds)
# release (Lua CAS so only the owner deletes)
LUA_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""
```

Lock TTL is `2*interval` so an extractor crash auto-recovers within a
predictable window without operator action.

## Migration

Three phases, each independently revertable.

**Phase 1 — Library work, no compose changes**

- Add `redis>=5` and `aioredis` (or `redis>=5` with asyncio) to dependencies.
- Add `redis` service to `docker-compose.yml` (no consumers yet).
- Create `uvo_pipeline/redis_client.py`, `streams.py`, `pubsub.py`, `locks.py`,
  `cache/`. Unit-test each.
- Move `_run_cross_source_dedup` from `orchestrator.py` to `uvo_pipeline/dedup.py`;
  generalize the `pipeline_run_id` filter to the `canonical_id is null AND
  ingested_at >= cutoff` predicate.
- Add `cache_backend` param to ITMS extractor with `MemoryCache` default.

**Phase 2 — Workers package + new services in Compose**

- Create `uvo_workers/runner.py`, source-specific entry modules.
- Add 6 new services to `docker-compose.yml` alongside the existing `pipeline`.
- Verify on a real run: extractors → streams; ingestor → Mongo; dashboard
  reflects fresh data; dedup-worker links cross-source matches on `notices:written`.
- Old `pipeline` is still wired but mostly skips (content-hash) since the new
  services are writing the same data first.

**Phase 3 — Cutover**

- `docker compose stop pipeline` (without removing it from the file yet).
  Confirm the dashboard remains healthy for a full cycle of every source —
  i.e. one Vestník cycle, one CRZ cycle, one TED cycle, one ITMS cycle, all
  reflected in `pipeline_state` and `notices` counts.
- Remove `pipeline` service from `docker-compose.yml`. Keep
  `uvo_pipeline.orchestrator.run()` reachable as `python -m uvo_pipeline ...`
  for ad-hoc backfills.

## Testing

- **Unit**: each new module (`streams`, `pubsub`, `locks`, `cache.redis`,
  `dedup`) gets focused tests using a real local Redis (via the existing
  `redis` Compose service started for tests) or `fakeredis`.
- **Worker integration**: a small test that runs `uvo_workers.runner` with a
  fake extract function for two cycles, asserts lock acquired/released and
  cycle metrics updated.
- **End-to-end**: existing `tests/e2e/` extended to start the new compose
  stack and verify a notice flows extractor → stream → ingestor → Mongo →
  dedup within seconds.
- **Backwards compatibility**: existing `tests/pipeline/` continues to pass —
  the orchestrator entry point is preserved for CLI use.

## Open questions

None at design time. All decisions are explicit above; revisit during
implementation only if a constraint surfaces (e.g. Redis memory ceiling on
the host, or Neo4j throughput limiting the ingestor).

## Cutover runbook (operator)

Phases 1 and 2 are merged. Phase 3 is the manual cutover the operator runs once
the new services are observed healthy:

1. Build images:
   `docker compose build redis extractor-vestnik extractor-crz extractor-ted extractor-itms ingestor dedup-worker`
2. Start the new stack alongside the legacy `pipeline`:
   `docker compose up -d redis extractor-vestnik extractor-crz extractor-ted extractor-itms ingestor dedup-worker`
   Content-hash skip in `upsert_batch` makes any double-write a no-op, so
   running both in parallel is safe.
3. Watch one full cadence cycle of every source — ITMS / CRZ / Vestník at 1 h,
   TED at 6 h. Confirm:
   - Stream backlog drains to ~0 (`docker compose exec redis redis-cli XLEN notices:vestnik` etc.).
   - `pipeline_state` checkpoints advance per source.
   - `cross_source_matches` count grows.
   - `/health` endpoints on ports 8091–8096 return 200 + JSON snapshots.
4. `docker compose stop pipeline` — keep the service definition in
   `docker-compose.yml` for now. Ad-hoc backfills still work via
   `docker compose run --rm pipeline run --mode historical` (or directly with
   `uv run python -m uvo_pipeline run` from a host with the source checkout).
5. After a clean week, optionally remove the `pipeline` block from
   `docker-compose.yml`. The Python entry point stays.

### Rollback

- Phase 2 rollback: `docker compose stop extractor-* ingestor dedup-worker; docker compose start pipeline`. Streams retain their backlog; the consumer group resumes on next start.
- Phase 1 rollback: revert the Phase 1 commit on a fresh branch and rebuild the
  `pipeline` image. ITMS extractor falls back to in-process `MemoryCache` when
  invoked with no `cache_backend` argument, so the legacy orchestrator path
  keeps working.
