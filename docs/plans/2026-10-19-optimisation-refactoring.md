# Optimisation & refactoring plan — 2026-10-19

Baseline: `main` @ `3428cd3`. Ruff clean, 582 unit tests green (85% coverage on core/api/mcp),
257 pipeline tests green. Sources: four read-only reviews (architecture, backend, ingestion, frontend/CI).

Finding IDs are prefixed by source review: **A** = architecture, **B** = backend, **P** = pipeline,
**G** = GUI/CI.

## Status

Status as of 2026-10-19, after the refactor merges. The wave tables below keep the original plan text
and file paths; where a path has since moved, the current location is in `CLAUDE.md` and `git log 3428cd3..main`.

- **Wave 1 (W1–W6): done, merged to `main`.**
- **Wave 2:**
  - Done: A01 (`uvo_core.adapters`, import-linter contract in CI), A04/B19 (`run_query` removed; routers call `uvo_core.services`), A13, A14 (single owner for search-index and Neo4j constraint bootstrap; shared cache-invalidation subscriber), A18 (`SourceSpec` + `run_extract`, `WorkerSettings`).
  - Done for API and MCP, partly done for workers: A09. Client factories live in `uvo_core.infra.clients` and are lifespan-owned in API and MCP. Workers build their handles in `uvo_workers/clients.py`. Switching workers to `uvo_core.infra.clients` is a remaining one-liner.
- **Also done:** A20 (`/readyz` with bounded Mongo ping on API and MCP; `/health` stays liveness).
- **Deferred:** the original items below are unchanged in intent. Items found during Wave 2 are added at the end of the table.

## Guardrails

- Merging to `main` builds images but does **not** deploy — prod is pinned by `sha-<tag>` in `stubarag-infra`.
  Nothing in this plan touches `stubarag-infra`, Vault, or live data.
- Changes that would rewrite production data or require coordinated env renames are **deferred** (see last section).
- Every workstream: TDD, `uv run ruff check src/ tests/` + full unit suite green before hand-back.

## Wave 1 — parallel workstreams (disjoint files)

### W1 · Ingestion reliability (data-pipeline agent) — branch `fix/ingestion-reliability`

| ID | Change | Files |
|----|--------|-------|
| P1/A06/A07 | Ack only successfully written entries; filter registry ops by failed indexes; check Neo4j `errors` | `uvo_pipeline/loaders/mongo.py`, `uvo_workers/ingestor.py` |
| P3 | Reclaim pending entries on a timer, page the XAUTOCLAIM cursor, dead-letter after K deliveries (split batch per entry) | `uvo_pipeline/streams.py`, `uvo_workers/ingestor.py` |
| P2/A15 | Producer backpressure (pause on group lag high-water mark); stop MAXLEN trimming from dropping unread entries | `uvo_pipeline/streams.py`, extractor flush loops |
| P8 | `xadd_many` via non-transactional pipeline | `uvo_pipeline/streams.py`, `uvo_core/adapters/redis/notice_stream.py`, extractors |
| P7/A16 | Checkpoint = cycle start − overlap, timezone-aware datetimes | `uvo_workers/{crz,ted,vestnik,itms}.py` |
| P11 | Shared `fetch_with_retry` (backoff, Retry-After, 5xx/timeout); never long-cache ITMS failures | `uvo_pipeline/extractors/*` |
| P16 | Collapse entity upserts by ICO within a batch | `uvo_pipeline/loaders/mongo.py` |
| P17 | Redis lock around dedup run | `uvo_workers/dedup.py` |
| P19 | Clear extractor `last_error` after a successful cycle | `uvo_workers/runner.py` |
| P20 | Batch ingestion-log inserts; log swallowed failures | `uvo_workers/ingestor.py`, `uvo_pipeline/ingestion_log.py` |
| P13 (part) | Metrics: stream lag, PEL size, dead-letter length, last success | `uvo_workers/metrics.py` |

### W2 · Backend query correctness & performance (developer agent) — branch `perf/backend-queries`

| ID | Change |
|----|--------|
| B1 | Honour `sort_by="value_desc"` for firma/dashboard top contracts |
| B2 | Procurer/supplier detail, summary, HHI over the full population (aggregation), not 100 rows |
| B5 | Fix `related_organisations` variable-length bound (Cypher can't parametrise it) + Cypher text test |
| B6 | Labelled, bounded `ego_network` (label match, hop cap, result limit, query timeout) |
| B7 | Neo4j `notice_cpv` index; date-range instead of `.year` accessor |
| B8 | Compound Mongo indexes: `{notice_type, publication_date}`, `{procurer.ico, notice_type}`, `{awards.supplier.ico, notice_type}`; ingestion-log `{component, ts}`; index-friendly monthly buckets match |
| B9/B16 | TTL-cache dashboard aggregates; include them in `clear_analytics_caches()` |
| B10/B11 | `asyncio.gather` for independent awaits (dashboard summary, risk profile, partners, timeline); `estimated_document_count` for entity totals |
| B12/B17 | `get_entity_by_ico` (`find_one` + projection) shared by firma and `/v1` |
| B14 | Ingestion-log/worker-status: gather counts, fold into `$group` |
| B20/B21 | Logged, per-branch error handling in unified search; cache fixes (`get_running_loop`, cancellation, retrieved exceptions, defensive copies) |
| B23 | Delete `routers/_agg.py` shim, unused private graph re-export |
| A20 | `/readyz` with bounded Mongo ping on API and MCP; liveness unchanged |

### W3 · Atlas Search hot path (search-tuner agent) — branch `perf/search-pipeline`

| ID | Change |
|----|--------|
| B3 | Filters as `compound.filter` inside `$search`; index-level sort; `$searchMeta` count; plain `find()` path when there is no text query |
| B13 | List projections (drop embeddings, large text) |
| B22 | Empty-query entity listing via indexed `find().sort()` |

Files: `uvo_core/adapters/mongo/{procurements,subjects}.py`, `uvo_core/search_query.py`, `uvo_mcp/search_indexes.py`.

### W4 · Frontend (frontend-dev agent) — branch `perf/gui-bundle`

| ID | Change |
|----|--------|
| G1/G2 | Route-level lazy loading + one `<Suspense>` in Layout; `manualChunks` vendor split |
| G3 | Delete dead `SearchPage`, `ConcentrationPage`, `CalendarPage`; re-point tests to `ZakazkyPage` |
| G5/G6 | Query-key factories (`firmaKeys`, `systemKeys`); pause polling in background |
| G7 | QueryClient defaults: no refetch on focus, no retry on 4xx, longer `staleTime` for aggregates, `placeholderData` on paginated queries, `queryClient` factory |
| G9 | Move hard-coded Slovak strings to `sk.ts`; fix "Hlavná navigácia" |
| G14 | One debounce constant; `AbortSignal` through `apiClient` |
| G15 | `@vitest/coverage-v8`; tests for firma tabs |
| G17 | nginx: gzip, immutable `/assets` caching, `no-cache` index, `worker_processes auto` |

### W5 · CI & images (devops agent) — branch `ci/pipeline-hardening`

| ID | Change |
|----|--------|
| G18 | `concurrency` groups; frontend job (lint, `tsc --noEmit`, vitest, build); add `gui` to image matrix |
| G19 | Publish gated on green CI; fix stale Swarm/k8s comments |
| G20/A11 | One parameterised multi-stage Python Dockerfile (cache mounts, pinned uv, no uv in runtime, `--chown`); keep the post-COPY `uv sync` and the CI import-check |
| G16 | GUI Dockerfile: npm cache mount, pinned base images |
| — | Remove the stray `.github/workflows/nginx.conf` if it's a duplicate |

### W6 · Dead code (developer agent) — branch `chore/remove-dead-modules`

A03: delete `catalog/ckan.py`, `extractors/vestnik_xml.py`, `utils/zip_handler.py`, `transformers/vestnik.py`,
`uvo_mcp/models.py`, `uvo_api/data/`, and the re-export shims (`uvo_mcp/cache.py`, `uvo_mcp/search_query.py`,
`uvo_pipeline/models.py`) — rewrite the tests that still import via shims. Drop the `ckan_packages` index.

## Wave 2 — layering (after Wave 1 merges; touches everything)

| ID | Change |
|----|--------|
| A01 | Break the `uvo_core ↔ uvo_pipeline` cycle: move streams/locks/pubsub/loaders/checkpoint into `uvo_core.adapters`; import-linter contract in CI |
| A04/B19 | Delete `run_query` string dispatcher; routers call typed `uvo_core.services` |
| A09 | Client factories with explicit timeouts and pool sizes; lifespan-managed clients; no module globals |
| A13/A14 | Single owner for search-index + Neo4j constraint bootstrap; shared cache-invalidation subscriber for API and MCP |
| A18/P14 | `SourceSpec` + one generic extractor loop; `WorkerSettings` base |

## Deferred — needs a decision from you

| ID | Why it's deferred |
|----|-------------------|
| P4 | Dedup pass 1 has no date window → over-merging. Fixing it **changes `canonical_id` on existing data**; needs a dry-run diff and your sign-off |
| P6 | `persist_match_groups` overwrites canonical_ids, leaves stale `cross_source_matches`; reconciliation migration |
| P5/P12 | Incremental dedup + `updated_at` BSON-date migration |
| A08 | Unify config / drop `API_` prefix — env var renames must land together with the Helm chart in `stubarag-infra` |
| A10 | Delete `deploy/` — harvest hardening into the `stubarag-infra` chart first |
| A02 | Delete `orchestrator.py` / pipeline image — first add a one-shot backfill mode to the workers |
| A17/A12 | Typed read-models; large function splits — after Wave 2 |
| F2 | Two definitions of contract count and total value. Entity docs from `recompute_entity_stats` count all notice types and use `final_value` only. `entity_profile` counts `contract_award` only, with a final→estimated fallback. Needs a product decision on the definition, then a stats recompute on existing data |
| — | Notices Atlas Search index rebuild on deploy. Text search returns nothing until the rebuilt index is READY. Measure rebuild time on prod-size data before rollout |
| — | Ego-network benchmark at prod volume. B6 bounds the query, but it has not been timed on prod-size data |
| — | CRZ extractor still retries only HTTP 429 (`uvo_pipeline/extractors/crz.py`). It does not use the shared `fetch_with_retry`, so 5xx and timeouts are not retried |
| — | `cpv_network` (`uvo_core/adapters/neo4j/graph.py`) lacks the null-ICO filter. `procurement_network` has `s.ico IS NOT NULL` since `17c3b13`, so the CPV graph can still show null-ICO supplier nodes |
| — | MCP Redis env in the Helm chart. MCP needs `REDIS_URL` and `REDIS_PASSWORD` in `stubarag-infra`; without them cache invalidation falls back to TTL with a warning. Local `docker-compose.yml` does not set them explicitly for `mcp-server` either; it relies on `.env` |
