# Cache policy

In-process TTL caches (`uvo_core.cache.async_ttl_cache`, backed by
`cachetools.TTLCache`) sit in front of the read queries. They live in each
service process (the API and the MCP server each hold their own); there is no
shared/distributed cache yet (see plan §5 — Redis-backed shared cache is
deferred until more than one API replica exists).

Concurrent identical calls share one in-flight coroutine, so a cold cache under
load issues a single Mongo query, not N. Results are deep-copied on the way out.

Every cache wrapper is labelled for Prometheus: `uvo_cache_requests_total{cache, result}`
(`hit`, `miss`, `inflight`) and `uvo_cached_call_duration_seconds{cache}` (time of
the underlying call on a miss). The label defaults to `<module>.<function>`, for
example `dashboards._summary_agg`; pass `name=` to override it.

## Policy table

All TTLs are seconds in the code; "min" and "h" are shown for readability.

| Query class | Function (module) | TTL | maxsize | Invalidation |
| ----------- | ----------------- | --- | ------- | ------------ |
| Query embedding | `embed` (`adapters/embedding.py`) | 5 min | 512 | TTL only (`depends_on_data=False`) |
| Procurement search | `search_procurements` (`adapters/mongo/procurements.py`) | 5 min | 256 | `notices:written` + TTL |
| Autocomplete dropdown | `run_autocomplete` (`adapters/mongo/autocomplete.py`) | 5 min | 512 | `notices:written` + TTL |
| Entity (procurer/supplier) search | `entity_search` (`adapters/mongo/subjects.py`) | 1 h | 256 | `notices:written` + TTL |
| Entity identity lookup | `get_entity_by_ico` (`adapters/mongo/entities.py`) | 5 min | 2000 | `notices:written` + TTL |
| Entity totals (`estimated_document_count`) | `entity_totals` (`adapters/mongo/entities.py`) | 10 min | 1 | `notices:written` + TTL |
| Company core stats (`$facet`) | `_firma_core_agg` (`adapters/mongo/analytics.py`) | 1 h | 500 | `notices:written` + TTL |
| Company partners | `_firma_partners_agg` (`adapters/mongo/analytics.py`) | 30 min | 200 | `notices:written` + TTL |
| Entity profile (HHI, spend by year) | `entity_profile` (`adapters/mongo/analytics.py`) | 30 min | 500 | `notices:written` + TTL |
| Market CPV + per-CPV median | `_market_cpv_agg` (`adapters/mongo/analytics.py`) | 24 h | 1 | `notices:written` + TTL |
| Legacy dashboard aggregates (`/api/dashboard/*`) | `_spend_by_year_agg`, `_cpv_breakdown_agg` (15 min, 256); `_monthly_buckets_agg` (15 min, 32); `_top_entities_agg` (30 min, 64); `_award_timeline_agg` (30 min, 500) (`adapters/mongo/analytics.py`) | see left | see left | `notices:written` + TTL |
| Analytics dashboards (`/api/analytics/*`) | `_summary_agg`, `_timeseries_agg`, `_top_agg`, `_concentration_agg`, `_cpv_agg` (`adapters/mongo/dashboards.py`) | 15 min | 512 | `notices:written` + TTL |
| Analytics coverage | `_coverage_agg` (`adapters/mongo/dashboards.py`) | 15 min | 1 | `notices:written` + TTL |
| Procurement detail | `fetch_procurement_detail` (`adapters/mongo/procurements.py`) | uncached | — | n/a (single indexed `find_one`) |

The analytics aggregates are keyed by the `DashboardFilter` (defaults applied)
plus the endpoint parameters. Analytics and legacy-dashboard entries therefore
never share a key.

## Why these TTLs

- **Search / autocomplete / embedding — 5 min.** High query diversity and a UX
  that expects near-fresh results. The short TTL mainly absorbs pagination and
  repeated identical queries.
- **Entity search and identity — 1 h / 5 min.** Name lookups change slowly, but
  identity lookups are cheap enough that a short TTL keeps them honest.
- **Company and entity-profile aggregates — 30 min to 1 h.** Per-company
  `$facet` / `$unwind` aggregations are relatively expensive; a company's award
  history changes on the order of days, not seconds.
- **Market CPV — 24 h.** A whole-corpus `$group` over every notice, feeding the
  market-deviation risk baseline. The distribution shifts slowly, so a long TTL
  is safe. This is the largest staleness window if an invalidation is missed.
- **Analytics dashboards — 15 min.** The corpus changes at most hourly. The
  dashboard aggregates scan the full filtered set (`maxTimeMS` 15 s), so a cache
  hit matters more than the exact freshness.
- **Procurement detail — uncached.** One indexed `find_one` is cheap.

## Invalidation

The ingestor publishes to the `notices:written` Redis pub/sub channel after each
write batch (`uvo_workers/ingestor.py`). The API (`uvo_api/app.py` lifespan) and
the MCP server (`uvo_mcp/server.py` lifespan) each run the subscriber
`run_cache_invalidator` (`uvo_core/adapters/redis/cache_invalidation.py`).

`async_ttl_cache` registers every cache with `depends_on_data=True` (the default)
in a module-level list. On an event the subscriber calls `clear_data_caches()`,
which clears all of them. Caches declared with `depends_on_data=False` (only
`embed`) survive. New caches need no registration.

The subscriber is **leading-edge debounced to one clear per 60 s**
(`DEBOUNCE_SECONDS`). An event that arrives inside the window is dropped, not
deferred. Consequence: the last write batch of a burst can leave caches holding
pre-batch data until their TTL expires (up to 15 min for analytics, 24 h for
market CPV). This is a known gap; a trailing clear would close it.

Redis is **best-effort** for invalidation: if it is unreachable the subscriber
logs once and exits, and the API and MCP keep serving from TTL-expiring caches.
No write path and no read path fails because invalidation is down.

### Warm-up

The API lifespan schedules `warm_default_dashboards()` 5 s after startup
(`uvo_api/app.py`, `_WARMUP_DELAY_SECONDS`). It pre-computes the landing-page
aggregates for the default period (summary, timeseries, top procurers and
suppliers, CPV division, coverage). It is best-effort: each job is independent and
a failure is logged at WARNING. The warm-up runs once per API start. It is not
re-run after an invalidation, so the first request after a `notices:written` clear
pays the cold cost.

### Dead code to remove

`uvo_core.adapters.mongo.analytics.clear_analytics_caches()` has no caller. The
subscriber uses `clear_data_caches()`, which already covers every cache in that
function's list. Remove `clear_analytics_caches()` in a follow-up change.
