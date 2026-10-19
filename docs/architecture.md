# UVO Search Architecture

## Overview

UVO Search searches and browses Slovak government procurement data. It has one React SPA, one HTTP API, one MCP server for LLM clients, and a set of ingestion workers. The API and the MCP server are two delivery adapters over the same query services in `uvo_core`.

1. **React SPA** (port 8080 in Docker, 5174 in dev) — public frontend, Slovak UI
2. **API** (`uvo_api`, port 8001) — FastAPI; calls `uvo_core.services` in-process
3. **MCP server** (`uvo_mcp`, port 8000) — FastMCP; exposes the same services as LLM tools
4. **Workers** (`uvo_workers`, ports 8091–8096) — ingest from five sources into Redis Streams, then into MongoDB and Neo4j
5. **Data sources** — UVO Vestník (XML), Ekosystem Datahub (CRZ), ITMS, TED, and NKOD (national open data catalog, used to discover Vestník datasets)

## System Architecture

```
  Browser                                   LLM clients
     │ HTTP                                   │ streamable-http / stdio
┌────▼─────────────────────┐        ┌─────────▼────────────────┐
│ React SPA (8080)         │        │ uvo_mcp (FastMCP, 8000)  │
│ nginx-served static app  │        │ thin tool wrappers       │
└────┬─────────────────────┘        └─────────┬────────────────┘
     │ /api/*                                 │
┌────▼─────────────────────┐                  │
│ uvo_api (FastAPI, 8001)  │                  │
│ routers → uvo_core       │                  │
└────┬─────────────────────┘                  │
     │          uvo_core.services  (in-process, shared)
     └──────────────────┬─────────────────────┘
                        │
        ┌───────────────┼────────────────┐
   MongoDB Atlas     Neo4j 5          Redis 7
   (notices, search) (graph)          (streams, pub/sub, locks)
                        ▲               ▲
                        │ upserts       │ XADD / XREADGROUP
              ┌─────────┴───────────────┴────────────┐
              │ uvo_workers                          │
              │ 4 extractors → ingestor → dedup-worker│
              └──────────────────────────────────────┘
```

## Process Architecture

### React SPA (port 8080, dev 5174)

- **Framework**: Vite + React 18 + TypeScript, Tailwind CSS, TanStack Query v5
- **Features**:
  - Client-side routing (React Router), with route-level lazy loading
  - URL-as-state (pagination, filters, sort, search in query params)
  - Search, filtering, sorting
  - Network graph visualization (Cytoscape.js, lazy-loaded chunk)
  - CPV trends and concentration analysis
- **Production serving**: nginx in the `gui-react` image, which proxies `/api` to the API service

### API (`uvo_api`, port 8001)

- **Framework**: FastAPI, served by uvicorn (`uv run python -m uvo_api`)
- **Routers**: `/api/*` for the SPA (contracts, procurers, suppliers, companies, dashboard, search, graph, ingestion, ingestion-log, worker-status) and `/v1/*` for the public API
- **Delivery adapter**: routers call typed functions in `uvo_core.services`. There is no HTTP hop and no string dispatcher.
- **Errors**: backend outages raise `uvo_core.errors.BackendUnavailable`, which one exception handler maps to 503
- **Clients**: Mongo, Neo4j, and Redis clients are created in the app lifespan and owned there
- **Operational endpoints**: `/api/dashboard/ingestion`, `/api/dashboard/ingestion-log`, and `/api/dashboard/worker-status` require a bearer ops token. An empty token disables the ingestion-log and worker-status routes.
- **Health**: `GET /health` (liveness), `GET /readyz` (bounded Mongo ping plus the required Atlas Search indexes; 503 otherwise)

**Port**: 8001 · **Bind host**: `0.0.0.0` (`API_HOST`)

### MCP Server (`uvo_mcp`, port 8000)

- **Framework**: FastMCP (Model Context Protocol)
- **Transports**: `streamable-http` (default, `uv run python -m uvo_mcp`) and `stdio` (`uv run python -m uvo_mcp stdio`, for Claude Desktop and Claude Code)
- **Tools**: thin wrappers over `uvo_core.services`. The full list is in [backend.md](backend.md#tools).
- **Caching**: in-process TTL caches in `uvo_core.cache`. A `notices:written` subscriber on Redis clears them; the API runs the same subscriber. If Redis is unreachable, the caches expire by TTL.
- **Health**: `GET /health` (liveness), `GET /readyz` (same check as the API)

**Port**: 8000 · **Bind host**: `0.0.0.0` (hard-coded in `uvo_mcp/server.py`)

### Workers (`uvo_workers`, ports 8091–8096)

Six long-lived processes, each run as `python -m uvo_workers.<service>`. See [data-pipeline.md](data-pipeline.md) for the full flow.

## Shared Core and Layering

`uvo_core` holds the query services, domain models, and infrastructure adapters. It imports none of the other packages.

| Module group | Contents |
| ------------ | -------- |
| `uvo_core.services` | Query services used by the API and MCP (search, graph, risk, entities) |
| `uvo_core.domain` | Models, CPV helpers, scoring, hashing, company merging |
| `uvo_core.adapters.mongo` | Loaders, dedup, ingestion log, checkpoints, search indexes, analytics, health |
| `uvo_core.adapters.neo4j` | Graph queries and the graph loader |
| `uvo_core.adapters.redis` | Streams, locks, pub/sub, cache invalidation, Redis client |
| `uvo_core.infra.clients` | Client factories with explicit timeouts and pool sizes |

`uvo_pipeline` holds source extractors and transformers, the `health` CLI, and the legacy one-shot orchestrator. Workers reuse its extractors.

import-linter enforces the layering in CI:

- `uvo_core` imports none of `uvo_pipeline`, `uvo_workers`, `uvo_api`, or `uvo_mcp`
- `uvo_core` and `uvo_pipeline` don't import the entrypoint packages
- `uvo_api`, `uvo_mcp`, and `uvo_workers` are independent of each other

## Communication Flow

### Browser → SPA → API → services → MongoDB

1. The user enters a query in the SPA.
2. TanStack Query calls `GET /api/contracts?...` (or another `/api` route).
3. The API router validates the parameters and calls a `uvo_core.services` function directly.
4. The service builds the Atlas Search or aggregation query and runs it against MongoDB (and Neo4j for graph routes).
5. The router returns JSON, and TanStack Query updates the cache.

### Claude Desktop / Claude Code → MCP Server (stdio)

1. Claude starts the server with `uv run python -m uvo_mcp stdio`.
2. Claude sends tool calls over stdin.
3. The tool calls the same `uvo_core.services` function the API uses.
4. The result goes back over stdout.

### Operational endpoints

- `GET /api/dashboard/ingestion` — pipeline health snapshot (source status, ingestion trends, dedup metrics)
- `GET /api/dashboard/ingestion-log` and `GET /api/dashboard/worker-status` — ops token required
- `GET /api/graph/ego/{ico}?hops=N` and `GET /api/graph/cpv/{cpv}?year=YYYY` — Neo4j-backed graph endpoints (Cytoscape-format JSON)
- `GET /api/procurers/{ico}/concentration?top_n=N` — supplier concentration (HHI)

## Key Design Decisions

### One service layer, two delivery adapters

Queries live once, in `uvo_core.services`. The API and MCP are adapters. Browser traffic does not pay an extra network hop, and a query fix lands in both surfaces at once. The MCP server stays a separate process because LLM clients connect to it over stdio or streamable-http, and it is not on the browser path.

### Redis Streams between extraction and storage

Extractors run on their own cadence and never write to the databases directly. The ingestor acks an entry only after both Mongo and Neo4j have accepted it. That gives redelivery through periodic reclaim, dead-lettering of poison entries, and backpressure on producers when the consumer falls behind.

### Typed errors at the boundary

`uvo_core` raises typed errors. Each delivery adapter maps them to protocol failures in one place: the API to HTTP status codes, and MCP to tool results.

## Data Flow: Search Example

**User enters "stavebnictvom" and clicks search:**

```
React SPA (Search page, TanStack Query)
  ↓
GET /api/contracts?q=stavebnictvom&...
  ↓
[uvo_api router] validates params, calls uvo_core.services.search
  ↓
[uvo_core.services.search] builds the Atlas Search query (sk_folding analyzer)
  ↓
[MongoDB Atlas Local] returns matched notices + total count
  ↓
[router] JSON response → [TanStack Query] updates cache → component re-renders
```

## Configuration & Environment

Settings are environment variables, loaded from `.env`. Prefixes matter: `ApiSettings` reads only `API_*`, and the other packages read unprefixed names. See `CLAUDE.md` for the `API_` prefix trap.

| Variable | Default | Read by | Purpose |
|----------|---------|---------|---------|
| `MONGO_PASSWORD` | *(required by compose)* | compose | MongoDB password |
| `NEO4J_PASSWORD` | *(required by compose)* | compose | Neo4j password |
| `API_MONGODB_URI` | *(required)* | `uvo_api` | MongoDB URI for the API. No default. |
| `API_NEO4J_URI` | unset | `uvo_api` | Neo4j URI; graph routes return 503 when unset |
| `API_REDIS_PASSWORD` | `""` | `uvo_api` | Redis password for `/v1` rate limiting |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8001` | `uvo_api` | API bind address |
| `REDIS_URL` | `redis://redis:6379/0` | workers, MCP | Redis URI |
| `REDIS_PASSWORD` | `""` | workers, MCP | Redis password |
| `EKOSYSTEM_BASE_URL` | `https://datahub.ekosystem.slovensko.digital` | MCP, pipeline | Ekosystem Datahub URL |
| `EKOSYSTEM_API_TOKEN` | *(optional)* | MCP, pipeline | Token for Ekosystem (not needed for public endpoints) |
| `TED_BASE_URL` | `https://api.ted.europa.eu` | MCP | TED API URL |
| `REQUEST_TIMEOUT` | `30.0` | MCP | HTTP request timeout (seconds) |
| `CACHE_TTL_SEARCH` | `300` | MCP | Search result cache TTL (seconds) |
| `CACHE_TTL_ENTITY` | `3600` | MCP | Entity lookup cache TTL (seconds) |
| `CACHE_TTL_DETAIL` | `1800` | MCP | Detail view cache TTL (seconds) |

Worker settings (intervals, stream limits, dedup, dead-letter) are listed in [reference.md](reference.md#environment-variables).

## Deployment

### Local Development

**Terminal 1 — MCP Server**:
```bash
uv run python -m uvo_mcp
```

**Terminal 2 — API**:
```bash
uv run python -m uvo_api
```

**Terminal 3 — React GUI**:
```bash
cd src/uvo-gui-react && npm run dev
```

The dev server proxies `/api` to port 8001. The MCP server is independent of the SPA.

### Docker Compose

```bash
docker compose up -d --build
```

The default stack has 12 services. Two more are opt-in profiles (`legacy` for the one-shot pipeline, `debug` for mongo-express).

- `mcp-server` (port 8000) — depends on healthy `mongo` and `neo4j`
- `api` (port 8001) — depends on healthy `mongo` and `neo4j`
- `gui-react` (port 8080) — depends on healthy `api`
- Four extractors, `ingestor`, `dedup-worker` — depend on healthy `redis`, `mongo`, and `ingestor`

The root `Dockerfile` builds the Python images via `--target mcp | api | workers | pipeline`. The GUI image is `src/uvo-gui-react/Dockerfile`.

### Production

Production runs on Kubernetes through ArgoCD, managed in the `stubarag-infra` repository. The conventions and images are in [CLAUDE.md](../CLAUDE.md#production-deployment--kubernetes-via-argocd). The `deploy/` directory in this repository is superseded.

## Monitoring & Observability

### Health Checks

| Service | Liveness | Readiness |
|---------|----------|-----------|
| API (8001) | `GET /health` | `GET /readyz` |
| MCP (8000) | `GET /health` | `GET /readyz` |
| Workers (8091–8096) | `GET /health` (JSON snapshot), `GET /metrics` | `GET /readyz` on the same port |
| React GUI (8080) | HTTP 200 on `/` (nginx static) | — |

`/readyz` on API and MCP returns 503 until MongoDB answers a bounded ping and the required Atlas Search indexes exist.

### Logging

All services use Python's `logging` module. Log levels are set in code; there is no `LOG_LEVEL` environment variable.

### Error Handling

**Frontend** (graceful degradation):
- API timeout → display error message, allow retry
- API 429 (rate limited) → show cached results if available
- Malformed response → "Chyba pri vyhľadávaní: {exception}"

**API**:
- `BackendUnavailable` → 503 with a generic detail; the reason is logged, never returned

**MCP Server**:
- Database not configured → tool returns an error dict with `status_code` 503
- Validation errors → rejected by FastMCP before the tool runs

## Data Pipeline

Six **long-lived microservices** ingest from five sources into MongoDB and Neo4j via Redis Streams:

```
UVO Vestník   Ekosystem/CRZ   ITMS        TED API     NKOD (discovery)
   (XML)          │             │            │             │
   └──────────────┴─────────────┴────────────┴─────────────┘
                         │ extractors (XADD notices:<source>)
                  ┌──────▼──────────────────────┐
                  │ Redis Streams               │
                  └──────┬──────────────────────┘
                         │ XREADGROUP
                  ┌──────▼──────┐   PUBLISH notices:written   ┌────────────┐
                  │ ingestor    ├───────────────────────────►│ dedup-worker│
                  └──────┬──────┘                            └──────┬──────┘
                         │ upserts                                  │
                  ┌──────▼──────────┐                               │
                  │ MongoDB / Neo4j │◄──────────────────────────────┘
                  └──────┬──────────┘
                         │ queries
                    API / MCP server
```

**Four extractors + ingestor + dedup-worker:**
- `extractor-vestnik`, `extractor-crz`, `extractor-ted`, `extractor-itms` — each owns its interval and rate-limit budget, and emits `CanonicalNotice` batches to `notices:<source>`
- `ingestor` — reads all four streams, upserts into Mongo and Neo4j, acks only fully written entries, and publishes `notices:written`
- `dedup-worker` — subscribes to `notices:written`, debounces 5 s, and runs cross-source dedup with an hourly fallback poll

The legacy `pipeline` service stays for ad-hoc backfills (`docker compose --profile legacy run --rm pipeline run --mode historical`).

**Per-service health endpoints** (JSON snapshots): 8091 (vestnik), 8092 (crz), 8093 (ted), 8094 (itms), 8095 (ingestor), 8096 (dedup-worker).

**Deduplication**:
- Per-source: `(source, source_id)` unique constraint
- Cross-source: event-driven on `notices:written`, with a 1 h fallback poll; guarded by the `dedup:lock` Redis lock

See [data-pipeline.md](data-pipeline.md) and the design spec at [docs/superpowers/specs/2026-04-27-source-microservices-design.md](superpowers/specs/2026-04-27-source-microservices-design.md). The spec is historical; the code and `CLAUDE.md` are authoritative where they differ.
