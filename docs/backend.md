# Backend Documentation

The backend is one shared core, two delivery adapters, and the ingestion workers:

- **`uvo_core`** — query services, domain models, and infrastructure adapters. Shared by everything else.
- **`uvo_api`** — FastAPI delivery adapter for the React SPA and the public `/v1` API (port 8001)
- **`uvo_mcp`** — FastMCP delivery adapter for LLM clients (port 8000)
- **`uvo_workers`** — long-lived ingestion services. See [data-pipeline.md](data-pipeline.md).

Both delivery adapters call the same functions in `uvo_core.services`. The API never calls the MCP server over HTTP.

## Key Files

### uvo_core (shared)

- `src/uvo_core/services/search.py` — procurement search, procurement detail, entity search, page clamping
- `src/uvo_core/services/graph.py`, `src/uvo_core/services/risk.py` — graph and company-risk services
- `src/uvo_core/adapters/mongo/` — notices, entities, analytics, ingestion log, Atlas Search indexes, health
- `src/uvo_core/adapters/neo4j/graph.py` — Cypher for ego networks, CPV networks, concentration
- `src/uvo_core/adapters/redis/` — streams, locks, pub/sub, cache invalidation
- `src/uvo_core/infra/clients.py` — Mongo, Neo4j, and Redis client factories with explicit timeouts and pool sizes
- `src/uvo_core/errors.py` — `BackendUnavailable`
- `src/uvo_core/cache.py` — async TTL cache decorator
- `src/uvo_core/testing.py` — helpers for tests

### uvo_mcp

- `src/uvo_mcp/__main__.py` — entry point; `stdio` argument selects the stdio transport
- `src/uvo_mcp/server.py` — FastMCP instance, `app_lifespan`, `/health`, `/readyz`
- `src/uvo_mcp/config.py` — `Settings` (environment variables)
- `src/uvo_mcp/tools/` — tool definitions (`procurements.py`, `subjects.py`, `graph.py`, `risk.py`, `autocomplete.py`, `vector_search.py`)

### uvo_api

- `src/uvo_api/app.py` — `create_app`, lifespan, `/health`, `/readyz`, router registration
- `src/uvo_api/__main__.py` — entry point (`uvicorn`, factory `create_app`)
- `src/uvo_api/config.py` — `ApiSettings` (`API_*` environment variables)
- `src/uvo_api/routers/` — `/api/*` routers; `routers/v1/` — public `/v1` API
- `src/uvo_api/_schema.py`, `models.py` — response models
- `src/uvo_api/auth.py`, `ratelimit.py` — ops-token guard and `/v1` rate limiting
- `src/uvo_api/errors.py`, `v1_errors.py` — exception handlers and the `/v1` error envelope

## Starting the Servers

```bash
# MCP server, streamable-http transport (default), port 8000
uv run python -m uvo_mcp

# MCP server, stdio transport (Claude Desktop / Claude Code)
uv run python -m uvo_mcp stdio

# API, port 8001
uv run python -m uvo_api
```

Both HTTP services bind `0.0.0.0`. The MCP bind address is hard-coded in `server.py`. The API reads `API_HOST` and `API_PORT`.

## MCP Server

### Lifespan

`app_lifespan` in `src/uvo_mcp/server.py` runs once per process:

1. Creates the Mongo, Neo4j, and Redis handles through `uvo_core.infra.clients`.
2. Bootstraps the Atlas Search indexes. A failure is logged at ERROR and is not fatal; `/readyz` reports the gap.
3. Starts background tasks, including the `notices:written` cache-invalidation subscriber.
4. Yields an `AppContext` (Mongo database, Neo4j driver, settings, embedding model when loaded). Tools read it from `ctx.request_context.lifespan_context`.
5. On shutdown, cancels the background tasks and closes the clients.

### Tools

Every tool is a thin wrapper over `uvo_core.services`. Tool names are the Python function names.

| Tool | Module | Parameters | Purpose |
|------|--------|------------|---------|
| `search_completed_procurements` | `tools/procurements.py` | `text_query`, `cpv_codes`, `procurer_id`, `supplier_ico`, `date_from`, `date_to`, `limit` (max 100), `offset` | Search completed government procurements |
| `get_procurement_detail` | `tools/procurements.py` | `procurement_id` | Full record for one procurement |
| `find_procurer` | `tools/subjects.py` | `name_query`, `ico`, `sort_by`, `limit`, `offset` | Search contracting authorities |
| `find_supplier` | `tools/subjects.py` | `name_query`, `ico`, `sort_by`, `limit`, `offset` | Search suppliers |
| `search_autocomplete` | `tools/autocomplete.py` | `query`, `types`, `limit` | Live suggestions per entity type |
| `search_companies_vector` | `tools/vector_search.py` | `query`, `limit`, `role` | Semantic search over company names (FastEmbed) |
| `company_risk_profile_tool` | `tools/risk.py` | `ico` | 0–100 red-flag score with per-flag evidence |
| `find_supplier_concentration` | `tools/graph.py` | `procurer_ico`, `top_n` | Top suppliers of one authority, by awarded value |
| `find_related_organisations` | `tools/graph.py` | `ico`, `max_hops` | Organisations connected through shared contracts |
| `get_procurement_network` | `tools/graph.py` | `cpv_code`, `year` | Procurer–supplier network for a CPV code and year |
| `graph_ego_network` | `tools/graph.py` | `ico`, `max_hops` | Ego network around one company (Cytoscape-style nodes and edges) |
| `graph_cpv_network` | `tools/graph.py` | `cpv_code`, `year` | CPV network (Cytoscape-style nodes and edges) |

`limit` is clamped by `clamp_page` to `max_page_size` (100), and `offset` to a fixed maximum. Graph tools bound their hops and result sizes in Cypher.

### Errors

- If MongoDB is not configured, the tool returns `{"error": "MongoDB not configured", "status_code": 503}` instead of raising.
- Backend exceptions are not caught inside the tools. FastMCP reports them as tool errors.

### Adding a Tool

1. Put the query in `uvo_core.services` (or reuse an existing function). The API can then use it too.
2. Add a thin wrapper in `src/uvo_mcp/tools/`:

   ```python
   # src/uvo_mcp/tools/subjects.py (or a new module imported at the bottom of server.py)
   @mcp.tool()
   async def my_new_tool(ctx: Context, ico: str, limit: int = 20) -> dict:
       """One-line description shown to the LLM."""
       app_ctx = _get_app_context(ctx)
       if app_ctx.mongo_db is None:
           return {"error": "MongoDB not configured", "status_code": 503}
       limit, _ = clamp_page(limit, 0, max_limit=app_ctx.settings.max_page_size)
       return await my_query(app_ctx.mongo_db, ico=ico, limit=limit)
   ```

3. Add the module to the import list at the bottom of `server.py` so the decorator runs.

### Health

- `GET /health` — liveness: `{"status": "ok", "service": "uvo-mcp"}`. Never checks dependencies.
- `GET /readyz` — readiness: 200 when a bounded Mongo ping succeeds and the required Atlas Search indexes exist (cached briefly). 503 otherwise.

## API (`uvo_api`)

### Application

`create_app` in `src/uvo_api/app.py` builds the FastAPI app, registers the error handlers, and mounts the `/v1` sub-app. The lifespan creates the Mongo, Neo4j, and Redis clients, stores them on `app.state`, and closes them on shutdown. The `/v1` sub-app shares those clients.

Routes under `/api/*` return the schemas in `uvo_api/_schema.py`. Public `/v1` routes are mounted under `/v1`.

### Routes

**Procurement and entity routes** (`/api/…`):

- `GET /api/contracts` — filters: `q`, `cpv`, `date_from`, `date_to`, `value_min`, `value_max`, `ico`, `supplier_ico`, `procurer_ico`, `limit`, `offset`
- `GET /api/contracts/{contract_id}` — contract detail
- `GET /api/procurers`, `GET /api/procurers/{ico}`, `GET /api/procurers/{ico}/summary`
- `GET /api/procurers/{ico}/concentration?top_n=N` — supplier concentration (HHI)
- `GET /api/suppliers`, `GET /api/suppliers/{ico}`, `GET /api/suppliers/{ico}/summary`
- `GET /api/firma/{ico}`, `GET /api/firma/{ico}/partneri`, `GET /api/firma/{ico}/cpv-profile` — company profile tabs (`/api/firmy` for the company list)
- `GET /api/search/entities`, `GET /api/search/unified` — entity and combined search

**Dashboard routes** (`/api/dashboard/…`):

- `GET /api/dashboard/summary` — KPI snapshot
- `GET /api/dashboard/spend-by-year`, `top-suppliers`, `top-procurers`, `by-cpv`, `by-month`, `recent`
- `GET /api/dashboard/ingestion` — pipeline health (source status, ingestion trends, dedup metrics)
- `GET /api/dashboard/ingestion-log` and `GET /api/dashboard/worker-status` — require the ops bearer token

**Graph routes** (`/api/graph/…`), Neo4j-backed:

- `GET /api/graph/ego/{ico}?hops=N` — `hops` 1–3, default 2; Cytoscape-format JSON
- `GET /api/graph/cpv/{cpv}?year=YYYY` — procurer–supplier–notice network; Cytoscape-format JSON

**Public API** (`/v1/…`): `/v1/companies` (list, `{ico}`, `{ico}/profile`, `{ico}/risk`) and `/v1/contracts` (list, `{contract_id}`). Requests are rate-limited through Redis, and errors use the envelope in `v1_errors.py`.

### Errors

- `uvo_core.errors.BackendUnavailable` is mapped to HTTP 503 by one exception handler. The reason is logged and never returned to the client.
- Graph routes return 503 when `API_NEO4J_URI` is unset.

### Health

- `GET /health` — liveness: `{"status": "ok", "service": "uvo-api"}`
- `GET /readyz` — readiness, same check as the MCP server

## Data Pipeline (Workers)

Six long-lived services ingest data through Redis Streams: four extractors (`extractor-vestnik`, `extractor-crz`, `extractor-ted`, `extractor-itms`), `ingestor` (port 8095), and `dedup-worker` (port 8096). The design, reliability rules, and configuration are in [data-pipeline.md](data-pipeline.md).

Health endpoints return JSON snapshots, and the same port serves `/readyz` and `/metrics`:

```bash
curl http://localhost:8091/health  # extractor-vestnik
curl http://localhost:8095/health  # ingestor
```

Key files:

- `src/uvo_workers/` — `runner.py`, `context.py`, `clients.py`, `extract.py` (`SourceSpec`, `run_extract`), `ingestor.py`, `dedup.py`, `metrics.py`, `health.py`
- `src/uvo_core/adapters/redis/streams.py` — XADD, XREADGROUP, XAUTOCLAIM, XACK, XTRIM helpers
- `src/uvo_core/adapters/redis/locks.py` — distributed lock helpers
- `src/uvo_core/adapters/mongo/dedup.py` — cross-source dedup logic

## Caching

Search results, entity lookups, and dashboard aggregates use the in-process TTL cache in `uvo_core/cache.py`. The TTLs are `CACHE_TTL_SEARCH`, `CACHE_TTL_ENTITY`, and `CACHE_TTL_DETAIL` (MCP settings). Cached aggregates are cleared by `clear_data_caches` / `clear_analytics_caches`. Both `uvo_api` and `uvo_mcp` run a `notices:written` subscriber that calls `clear_data_caches()`. It is debounced, and it stops quietly if Redis is unreachable, after which the caches expire by TTL.

## Storage Mapping

The services read from MongoDB and Neo4j. The workers write to both.

| Feature | Store | Access |
|---------|-------|--------|
| Procurement search and detail | MongoDB `notices` | Atlas Search (`sk_folding` analyzer) or `find` / aggregation when there is no text query |
| Procurer and supplier search | MongoDB `procurers`, `suppliers` | Atlas Search (`autocomplete` edgeGram subfield) and `ico` equality |
| Company risk, dashboard aggregates | MongoDB `notices` and entity collections | Aggregation pipelines |
| Semantic company search | MongoDB vector index | `$vectorSearch` over FastEmbed embeddings |
| Graph routes and tools | Neo4j | Cypher (`uvo_core/adapters/neo4j/graph.py`) |

## Testing

Tests live in `tests/` (`core/`, `api/`, `mcp/`, `workers/`, `pipeline/`, `gui/`) plus `tests/e2e/`, which needs `docker compose up`.

```bash
uv run pytest tests/ --ignore=tests/e2e -q   # unit suite
uv run pytest tests/mcp/ -v                  # MCP only
```

Shared fixtures are in `tests/conftest.py`. The API fixtures are in `tests/api/conftest.py` and `tests/api/_deps.py`. Unit tests use `mongomock-motor`, `fakeredis`, and `respx`. Tests for the Neo4j layer assert on query text and parameters.

## Logging

The workers and the pipeline CLI configure `logging` at INFO in code. There is no `LOG_LEVEL` environment variable.
