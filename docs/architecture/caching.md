# Cache policy

In-process TTL caches (`uvo_core.cache.async_ttl_cache`, backed by
`cachetools.TTLCache`) sit in front of the read queries. They live in each
service process (the API and the MCP server each hold their own); there is no
shared/distributed cache yet (see plan §5 — Redis-backed shared cache is
deferred until more than one API replica exists).

Concurrent identical calls share one in-flight coroutine, so a cold cache under
load issues a single Mongo query, not N.

## Policy table

| Query class | Function | TTL | maxsize | Invalidation |
| ----------- | -------- | --- | ------- | ------------ |
| Procurement search | `adapters/mongo/procurements.py:search_procurements` | 5 min | 256 | TTL only |
| Autocomplete dropdown | `adapters/mongo/autocomplete.py:run_autocomplete` | 5 min | 512 | TTL only |
| Query embedding | `adapters/embedding.py:embed` | 5 min | 512 | TTL only |
| Entity (procurer/supplier) search | `adapters/mongo/subjects.py:entity_search` | 1 h | 256 | TTL only |
| Company core stats (`$facet`) | `adapters/mongo/analytics.py:_firma_core_agg` | 1 h | 500 | **`notices:written`** + TTL |
| Company partners | `adapters/mongo/analytics.py:_firma_partners_agg` | 30 min | 200 | **`notices:written`** + TTL |
| Market CPV + per-CPV median | `adapters/mongo/analytics.py:_market_cpv_agg` | 24 h | 1 | **`notices:written`** + TTL |
| Procurement detail | `adapters/mongo/procurements.py:fetch_procurement_detail` | uncached | — | n/a (single indexed `find_one`) |
| Dashboard aggregations (`spend_by_year`, `cpv_breakdown`, `monthly_buckets`, `top_suppliers/procurers`, `award_timeline`) | `MongoCompanyAnalytics` methods | uncached | — | n/a (always reflect full corpus) |

## Why these TTLs

- **Search / autocomplete / embedding — 5 min.** High query diversity and a UX
  that expects near-fresh results. The short TTL mainly absorbs pagination and
  repeated identical queries; it bounds staleness to a few minutes.
- **Entity search — 1 h.** Name→entity lookups change slowly. The per-row
  contract stats it returns are now denormalized onto the entity documents
  (`contract_count`/`total_value`, see below), so this query no longer scans
  `notices` and can be cached longer cheaply.
- **Company core stats / partners — 1 h / 30 min.** Per-company `$facet` /
  `$unwind` aggregations are relatively expensive; a company's award history
  changes on the order of days, not seconds.
- **Market CPV — 24 h.** A whole-corpus `$group` over every notice — the most
  expensive read in the system — feeding the market-deviation risk baseline.
  The market distribution shifts slowly, so a long TTL is safe. This is the
  single biggest staleness window and the primary reason the invalidation hook
  exists.
- **Detail / dashboard — uncached.** Detail is one indexed `find_one` (cheap).
  Dashboard aggregations were deliberately left uncached in Phase 3 (they
  replaced the old sampled endpoints); correctness over the full corpus wins
  over shaving a re-aggregation.

## Invalidation

The ingestor publishes to the `notices:written` Redis pub/sub channel after each
write batch (`uvo_workers/ingestor.py`). The API subscribes for the app's
lifetime (`uvo_api/cache_invalidation.py`, wired via the FastAPI lifespan) and,
on any event, clears the three **analytics** caches
(`clear_analytics_caches()`), which carry the longest TTLs (up to 24 h). This is
**debounced to at most one clear per 60 s** so bulk ingestion (many batches per
second during a backfill) doesn't thrash the caches.

The short-TTL caches (search, autocomplete, embedding, entity) are **not**
invalidated on write — a ≤1 h natural expiry is not worth coupling every write
to every read cache. The dedup worker already listens to the same channel to
trigger cross-source dedup, so the publisher was in place before this hook.

Redis is **best-effort** for invalidation: if it is unreachable the subscriber
logs once and exits, and the API keeps serving from TTL-expiring caches — the
same tolerance the `/v1` rate limiter applies to Redis. No write path and no
read path fails because invalidation is down.
