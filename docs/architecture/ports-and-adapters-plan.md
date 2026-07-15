# uvo-search — Ports-and-Adapters Refactor & Optimization Plan

Prepared 2026-07-14. All paths relative to repo root. v1 branch paths refer to `worktree-agent-a43a13f157a4f31bd`.

---

## 1. Current-State Assessment

### 1.1 The dual read path (the central inconsistency)

`uvo_api` reads data two ways, and the split is arbitrary per endpoint:

**Path A — HTTP hop through MCP:** `src/uvo_api/mcp_client.py:23-43` → `uvo_mcp` tools → Mongo.
**Path B — direct Motor client:** `src/uvo_api/db.py:11-17` → aggregation pipelines in routers.

Concrete evidence of the split *inside single endpoints*:
- `src/uvo_api/routers/firma.py:48-51` — `get_firma_profile` gathers 2 MCP calls **and** a direct-Mongo `_firma_core_agg` in the same `asyncio.gather`.
- `src/uvo_api/routers/dashboard.py` — `top_suppliers`/`top_procurers` (lines 158-217) are direct Mongo pipelines; `dashboard_summary`/`spend_by_year`/`by_cpv`/`by_month` (lines 80-284) go through MCP paging.
- The v1 prototype inherits both: `routers/v1/companies.py:147-151` gathers `call_tool(...)` + `_firma_core_agg(db, ...)`.

CLAUDE.md still says "the GUI goes through `mcp_client.call_tool` — don't bypass it," but main already bypasses it (commit `76dd433`). The rule is dead; the refactor should bury it officially.

**Import inversion:** `src/uvo_api/routers/_agg.py:5` does `from uvo_mcp.cache import _make_key, async_ttl_cache` — the API package imports a *private* helper from the MCP server package. `uvo_api` hard-depends on `uvo_mcp` at import time.

### 1.2 Where domain logic is tangled with infrastructure

| Domain logic | Where it lives today | Tangled with |
|---|---|---|
| Cross-source duplicate matching (passes 1–2) | `src/uvo_pipeline/dedup.py:205-330` | Clustering rules interleaved with Mongo writes inside the loop. Pass 3 is already correctly split: pure `build_ico_value_window_groups` (44-162) + `persist_match_groups` (165-181). Passes 1–2 never got the same treatment. |
| Company merge-by-ICO + role resolution | Duplicated **3×**: `firma.py:271-300`, `search.py:83-94`, v1 `companies.py:38-67` | Three drifting copies in FastAPI routers; `search.py:97-134` has a 4th variant. |
| Primary-role heuristic | `firma.py:85-92` | Router body. |
| **CPV concentration (HHI)** — first risk-scoring logic in the codebase | v1 `companies.py:121-140` | Computed inline in a router. The red-flag engine will build on this; it's born in the wrong layer. |
| Supplier-concentration risk query | `src/uvo_mcp/tools/graph.py:17-47` | Cypher embedded in an MCP tool; unreachable from FastAPI/v1 without the HTTP hop. |
| Search relevance ranking | `search.py:189-197` | Router body. |
| Dashboard deltas / per-year stats | `dashboard.py:98-130` | Computed in Python over a 500-doc *sample* (see 1.3.2). |

**Counter-finding:** the transformers are already pure functions `raw dict → CanonicalNotice` (e.g. `transformers/crz.py:133-152`). The actual write-side tangle is in the **extractor workers** (`uvo_workers/vestnik.py:40-133` mixes checkpoints, extraction, transformation, hashing, and Redis xadd in one function) and the legacy `orchestrator.py:79-363` (285-line monolith).

### 1.3 Genuine optimization findings

1. **Per-request MCP client session** — `mcp_client.py:26-29`: every `call_tool` opens a fresh TCP connection + MCP `initialize()` handshake. `get_firma_profile` = 5 connections + 5 handshakes per request. Dominant per-request overhead in the API tier.
2. **Sampled aggregations are wrong, not just slow** — `dashboard.py:28-29,53-67`: `_fetch_contracts_sample` pages max 5×100 docs serially through MCP; `dashboard_summary`, `spend_by_year`, `by_cpv`, `by_month` aggregate in Python over that 500-doc sample — silently truncated numbers. `by_month` (257-284) fetches 500 unfiltered docs to answer a per-year question.
3. **Per-row `$lookup` in entity search** — `uvo_mcp/tools/subjects.py:65-118`: `contract_count`/`total_value` computed via a `$lookup` scanning `notices` per entity row. v1 `search_companies` requests 100+100 rows per page → up to 200 notice-scans for 20 rows. Fix: denormalize counts onto `procurers`/`suppliers`.
4. **Per-document upserts in the loader** — `loaders/mongo.py:204-283`: one `update_one`/`insert_one` per notice ×2 plus per-entity upserts (~3N round trips) instead of ~3 `bulk_write`s.
5. **Connection churn in workers** — `uvo_workers/dedup.py:107` creates a new Motor client per dedup run; `vestnik.py:45` per extract cycle. `runner.py` already holds a long-lived client; callbacks should receive it.
6. **Double caching, no invalidation** — same data TTL-cached in `uvo_mcp` tools AND in `uvo_api` (`_agg.py:8-12`, up to 24h). Ingestion writes never invalidate; `notices:written` pub/sub exists but only dedup listens.
7. **Post-pagination filtering bug** — `routers/contracts.py:48-57`: `value_min`/`value_max` filter the already-paginated page in Python and reset `total = len(rows)` — wrong totals, rows dropped mid-page. Belongs in the query.
8. **Full-document dedup candidate fetch** — `dedup.py:259` loads entire notices with no projection (pass 3 at 68-70 projects correctly).

### 1.4 The v1 API (prototype branch)

Well-shaped delivery layer (standalone sub-app, hashed keys, per-plan Redis rate limits, usage metering) but it consumes the same tangled read paths — every v1 request pays the MCP handshake tax and the merge-logic duplication. Phases 2–3 directly cheapen every future v1 endpoint.

---

## 2. Target Architecture

### Decision record 1 — introduce `uvo_core`, keep the four service packages as adapters

- **Context:** domain logic scattered across routers, MCP tools, and pipeline modules; upcoming features (scoring, risk, COI, sanctions, alerts) all need Mongo aggregates + graph queries + pure computation.
- **Decision:** one new package `src/uvo_core/` holding domain models, domain services, ports (`typing.Protocol`), and application query services. `uvo_api`/`uvo_mcp`/`uvo_workers` become delivery/driving adapters; Mongo/Neo4j/Redis code becomes driven adapters in `uvo_core/adapters/`.
- **Consequences:** (+) scoring engine pure and testable without a DB; (+) FastAPI and FastMCP expose the same service functions, ending the dual path; (−) one more package; (−) import churn (mitigated by re-export shims).

### Decision record 2 — kill the intra-cluster MCP HTTP hop; keep FastMCP as an external delivery adapter

- **Context:** React → uvo_api → HTTP+MCP framing → uvo_mcp → Mongo is a double hop with per-call handshakes. MCP is valuable as an LLM-agent product surface; as internal RPC it's pure overhead and forces double caching.
- **Decision:** extract the ~pure query helpers (`_search_mongo_procurements`, `_run_entity_search`, `_vsearch`/`_embed`, graph Cypher) into `uvo_core/services/`; MCP tools and FastAPI routers both call them in-process. `uvo_api/mcp_client.py` deleted (deprecation shim for one release).
- **Consequences:** (+) removes 2 hops + N handshakes per request — the biggest v1 latency win; (+) one cache layer; (+) compose dependency `api → mcp-server` disappears; (−) `uvo_api` needs fastembed only if serving vector search (optional constructor arg; degrades as today); (−) both services hold Mongo pools (they already do).
- **Rejected:** persistent MCP session pool — cheaper (S) but keeps the double hop, double cache, and marshalling; doesn't help scoring.

### Decision record 3 — ports as `Protocol`s, wiring via composition roots; no DI framework, no UoW, no generic EventBus

Each port: one production impl + optional in-memory fake. Composition roots: `uvo_api/app.py` lifespan, `uvo_mcp/server.py` `app_lifespan` (keep the `AppContext` shape), each worker `main()`. Zero new dependencies; mypy checks conformance structurally.

### Package layout

```
src/uvo_core/
  domain/
    models.py          # CanonicalNotice etc. moved from uvo_pipeline/models.py (shim re-export left behind)
    companies.py       # merge_by_ico, resolve_roles, primary_role  (from firma/search/v1 triplication)
    dedup.py           # PURE pass-1/2/3 group builders (mirror build_ico_value_window_groups)
    scoring.py         # phase 4: red flags, HHI, procurer risk — pure functions over domain inputs
    ranking.py         # search-hit ranking (from search.py:189-197)
  ports.py             # NoticeRepository, CompanyRepository, CompanyAnalytics,
                       # GraphStore, NoticeStream, CheckpointStore  (Protocols)
  services/
    search.py          # procurement/entity/vector/unified search use-cases
    company_profile.py # profile assembly (from firma.py:44-179 / v1 companies.py:144-212)
    dashboard.py       # dashboard use-cases (real aggregations)
    dedup.py           # orchestrates domain.dedup builders + repo.persist_match_groups
  adapters/
    mongo/             # repositories, aggregation pipelines (_agg.py, loaders/mongo.py, search_query.py move here)
    neo4j/             # GraphStore impl (loaders/neo4j.py + tools/graph.py Cypher)
    redis/             # streams.py, pubsub.py, locks.py, redis_client.py move here
    embedding.py       # fastembed wrapper (Embedder)
  cache.py             # async_ttl_cache moved from uvo_mcp/cache.py

src/uvo_api/           # FastAPI delivery adapter only (routers → services; /v1 sub-app with auth/ratelimit)
src/uvo_mcp/           # FastMCP delivery adapter only (tools → services)
src/uvo_workers/       # driving adapters: extract loops → source funcs + NoticeStream + CheckpointStore
src/uvo_pipeline/      # shrinks to: extractors/ + transformers/ + catalog/ + utils/ + legacy CLI shim
```

### Port specifications

| Port | Key methods | Earns its keep because |
|---|---|---|
| `NoticeRepository` | `search(NoticeQuery) -> Page[Notice]`, `get_by_source_id`, `upsert_batch`, `find_dedup_candidates(filter, projection)`, `persist_match_groups(groups)` | 4 consumers today (MCP tools, /api, /v1, dedup worker) + scoring engine. In-memory fake replaces mongomock for domain tests. |
| `CompanyRepository` | `find(name_query \| ico, sort, page)`, `vector_search(embedding, role)`, `upsert_procurer/supplier` | Same consumers; isolates the `$lookup` pipeline so denormalization is one adapter change. |
| `CompanyAnalytics` | `core_stats(ico)`, `partners(...)`, `market_cpv(limit)`, `top_suppliers/top_procurers(n)`, `spend_timeseries(filter)`, `monthly_buckets(year)` | The read-model the scoring engine consumes; keeps scoring's dependency surface explicit and small. |
| `GraphStore` | `ego_network`, `cpv_network`, `supplier_concentration`, `merge_notice_batch`, `ensure_constraints`; later `conflict_of_interest(ico)` | COI queries are a paid feature; today's Cypher is trapped inside MCP tools. |
| `NoticeStream` | `xadd_notice`, `read_group`, `ack`, `publish/subscribe` | Move + Protocol of existing `streams.py`/`pubsub.py`; alerts worker subscribes later. |
| `CheckpointStore` | `get(source)`, `save(source, state)` | Removes per-cycle Mongo clients from extractor workers; trivially faked. |

### Explicitly NOT abstracted (over-engineering guards)

- **No `SourceGateway` ABC** — extractors are already isolated async generators; one impl per source, zero swap scenarios.
- **No generic EventBus** — Redis Streams is the bus; `NoticeStream` names the use, not a pluggable transport.
- **No UnitOfWork/transactions** — writes are idempotent upserts; crash recovery is re-run, by design.
- **No repository for `ingestion_log`** — ops telemetry, stays a helper.
- **No port for rate-limiting/auth/metering** — delivery middleware; fakeredis covers tests.
- **No query-builder over Atlas Search** — pipelines move verbatim; port signature is domain-shaped, pipeline stays Mongo-specific.
- **No `Embedder` port beyond a thin optional wrapper**; degrade-on-unavailable preserved.
- **`SanctionsRepository` deferred** until the sanctions source is chosen.

---

## 3. Migration Roadmap (strangler; shippable after every phase)

Assumption: the v1 branch merges roughly as-is before refactor work starts; phases then update v1 routers in place.

### Phase 0 — Merge /v1 (S)
Merge the prototype branch (resolve against dedup/health/crz changes).
**Acceptance:** `/v1/docs` serves; v1 tests green on main; `/api` untouched.

### Phase 1 — `uvo_core` skeleton + dependency hygiene (S)
Create `src/uvo_core/`; move `uvo_mcp/cache.py` → `uvo_core/cache.py` (shim behind); fix `_agg.py:5` import; move `uvo_pipeline/models.py` → `uvo_core/domain/models.py` with re-export (stream payloads are JSON — schema unchanged); extract `domain/companies.py` from the merge-by-ICO triplication, point all four call sites at it.
**Acceptance:** `grep -r "from uvo_mcp" src/uvo_api` empty; one merge implementation; suite green; ruff clean.

### Phase 2 — Remove the MCP hop (M)
Move query fns into `uvo_core/services/` + `adapters/`; MCP tools become ≤10-line wrappers (signatures/output shapes byte-identical — MCP clients are external consumers); `uvo_api` lifespan constructs services with its Motor client + optional Embedder + Neo4j driver; replace every `call_tool(...)` in `/api` and `/v1` with service calls; delete per-call session code; drop `api → mcp-server` compose dependency; rewrite the stale CLAUDE.md rule.
**Acceptance:** `/api` + `/v1` fully functional with mcp-server stopped; MCP tool responses unchanged (golden-response test); firma profile p50 measurably down; single cache layer per query.

### Phase 3 — Repositories + aggregation correctness (M)
Define `ports.py`; wrap moved pipelines as Mongo/Neo4j adapters; replace sample-based dashboard endpoints with real aggregations (fixes 500-doc truncation); push `value_min/max` into the query (fixes contracts.py bug); move HHI into `domain/scoring.py`; add projection to dedup pass-2 fetch.
**Acceptance:** dashboard totals equal direct mongosh aggregation on the full corpus; contracts value-filter returns correct totals; in-memory fake repo exists, domain tests run with no DB.

### Phase 4 — Scoring engine: first pure-domain consumer (M)
`domain/scoring.py` red flags computable from existing data: supplier-concentration HHI per procurer, repeated same-pair awards, spend-vs-CPV-market deviation, single-supplier year share, short-interval award clusters. `services/risk.py` consuming only `CompanyAnalytics` + `GraphStore`. Expose as `/v1/companies/{ico}/risk` + one MCP tool.
This phase **validates the port design** — if scoring needs to import motor, phase 3 was done wrong.
**Acceptance:** scoring unit tests run against fakes with zero containers; endpoint in `/v1/docs`; flag semantics reviewed against zákon 343/2015.

### Phase 5 — Write side & dedup purification (M/L)
Split dedup passes 1–2 into pure builders + shared `persist_match_groups` (copy pass-3 pattern); convert `upsert_batch` to 3 `bulk_write`s (keep registry hash-skip semantics); workers take `CheckpointStore` + `NoticeStream` (removes per-cycle clients); demote `orchestrator.py` to thin backfill CLI or delete.
**Acceptance:** health invariants hold after a full worker cycle; dedup dry-run produces identical groups before/after; ingest throughput not regressed.

### Phase 6 — Connection/cache polish (S)
Settings singletons; documented cache policy (TTLs per query class); optional invalidation hook on `notices:written`; denormalized `contract_count/total_value` on entities (kills the per-row `$lookup`).
**Acceptance:** one Settings construction per process; entity search p95 down after denormalization.

**Implemented:**
- Settings are constructed once per process via `@lru_cache` factory functions
  (`get_settings` / `get_pipeline_settings` / `get_redis_settings` and the
  per-worker equivalents), replacing the per-call/per-cycle `Settings()` sites.
- Cache policy is documented in [`caching.md`](caching.md). The API subscribes to
  `notices:written` (`uvo_api/cache_invalidation.py`, via the FastAPI lifespan)
  and clears the analytics caches, debounced to ≤ once/60 s; degrades gracefully
  when Redis is down.
- `contract_count`/`total_value` are denormalized onto `procurers`/`suppliers`
  (recompute-only, see `scripts/backfill_entity_stats.py`); `entity_search` reads
  the stored fields instead of the per-row `$lookup` over `notices`.

**Parallelizable:** Phase 4 can start against port interfaces while phase 3 adapters finish; phase 5 independent of 4; phase 6 items are fillers.

---

## 4. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Moving Atlas `$search` pipelines subtly changes relevance | Move byte-identical; golden tests asserting equality of built pipeline dicts; search-tuner review. |
| MCP tool output drift breaks external LLM clients | Exact signatures + JSON shapes; contract test replays recorded calls old vs new. |
| mongomock can't express `$search`/`$facet` | Already true today; port fakes increase domain coverage; e2e suite remains the adapter safety net. |
| v1 merge conflicts with refactor churn | Phase 0 merges first; phases 2–3 update v1 routers in the same PRs that move their dependencies. |
| Import churn breaks scripts/ | Re-export shims for one release; grep `scripts/` in each move PR. |
| Solo-dev capacity — refactor stalls | Every phase leaves a coherent system; hard stop-line after phase 4 still delivers the monetization payoff. |
| Correct aggregations disagree with GUI expectations built on sampled numbers | Phase-3 tester harness quantifies the delta first; announce as a data-accuracy fix. |

## 5. Explicitly Deferred

- Sanctions adapter/port — until the source is chosen.
- Alerts worker — after phase 4 (~S once ports exist).
- Redis-backed shared cache — only past one API replica.
- Managed Atlas migration — ops track, orthogonal.
- Neo4j write-model redesign (richer COI edges) — needs external registry data.
- Any React GUI contract change — `/api` shapes frozen throughout.
