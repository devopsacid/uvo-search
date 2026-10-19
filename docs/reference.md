# Reference Guide

Quick lookup reference for developers.

## MCP Tool Signatures

All tools return JSON-serializable dicts. Tool names are the Python function names. Failures are reported as `{"error": ..., "status_code": ...}` where the tool handles them, or as MCP tool errors otherwise (see [backend.md](backend.md#errors)). The MCP endpoint is `POST /mcp` for streamable-http, or stdio with `uv run python -m uvo_mcp stdio`.

### search_completed_procurements

```
Module:     uvo_mcp.tools.procurements
Parameters:
  text_query (str, optional)       Full-text search query
  cpv_codes (list[str], optional)  EU product classification codes
  procurer_id (str, optional)      Filter by authority ID
  supplier_ico (str, optional)     Filter by supplier company number
  date_from (str, optional)        Start date (YYYY-MM-DD)
  date_to (str, optional)          End date (YYYY-MM-DD)
  limit (int, default 20)          Page size (max 100)
  offset (int, default 0)          Result offset

Returns:
  {"items": [...], "total": int, "limit": int, "offset": int}
```

### get_procurement_detail

```
Module:     uvo_mcp.tools.procurements
Parameters:
  procurement_id (str, required)

Returns: the full notice document.
Error:   {"error": "Procurement {id} not found", "status_code": 404}
```

### find_procurer and find_supplier

```
Module:     uvo_mcp.tools.subjects
Parameters:
  name_query (str, optional)       Name search (substring, wildcard, or phrase)
  ico (str, optional)              Company registration number (exact)
  sort_by (str, default "name")    Sort order
  limit (int, default 20)          Page size (max 100)
  offset (int, default 0)          Result offset

Returns:
  {"items": [...], "total": int, ...}
```

### Other tools

| Tool | Module | Parameters |
|------|--------|------------|
| `search_autocomplete` | `tools.autocomplete` | `query`, `types` (optional list), `limit` (default 5) |
| `search_companies_vector` | `tools.vector_search` | `query`, `limit` (default 10), `role` (default `"all"`) |
| `company_risk_profile_tool` | `tools.risk` | `ico` |
| `find_supplier_concentration` | `tools.graph` | `procurer_ico`, `top_n` (default 10) |
| `find_related_organisations` | `tools.graph` | `ico`, `max_hops` (default 2) |
| `get_procurement_network` | `tools.graph` | `cpv_code`, `year` |
| `graph_ego_network` | `tools.graph` | `ico`, `max_hops` (default 2) |
| `graph_cpv_network` | `tools.graph` | `cpv_code`, `year` |

## Frontends

The public SPA lives in [`src/uvo-gui-react/`](../src/uvo-gui-react/) (React 18 + Vite + TanStack Query). It calls the API on port 8001 under `/api/...`. The API calls `uvo_core.services` in-process. The SPA does not talk to the MCP server. See the package's `README.md` for routes, components, and dev instructions.

## Environment Variables

Settings are read from the environment and from `.env`. `ApiSettings` reads only `API_*` names. Every other package reads unprefixed names. See `CLAUDE.md` for the `API_` prefix trap.

**Storage and credentials** (compose requires the first two):

| Variable | Default | Purpose |
|----------|---------|---------|
| `MONGO_PASSWORD` | *(required)* | MongoDB user password |
| `NEO4J_PASSWORD` | *(required)* | Neo4j user password |
| `MONGODB_URI` | — | MongoDB URI for MCP and the workers |
| `NEO4J_URI` | — | Neo4j URI for the workers and MCP |
| `API_MONGODB_URI` | *(required, no default)* | MongoDB URI for the API |
| `API_NEO4J_URI` | unset | Neo4j URI for the API; graph routes return 503 when unset |
| `API_NEO4J_USER` / `API_NEO4J_PASSWORD` | — | Neo4j credentials for the API |
| `API_REDIS_PASSWORD` | `""` | Redis password for the API (`/v1` rate limiting) |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8001` | API bind address and port |
| `API_CORS_ORIGINS` | `http://localhost:5174`, `http://localhost:8080` | Allowed browser origins (list) |
| `API_OPS_TOKEN` | `""` | Bearer token for ops endpoints; empty disables them |
| `API_DOCS_ENABLED` | `false` | Expose interactive API docs |

**Redis** (workers, MCP, and API):

| Variable | Default | Purpose |
|----------|---------|---------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URI |
| `REDIS_PASSWORD` | `""` | Redis password. MCP needs it for the `notices:written` cache-invalidation subscriber |

**Workers — extractor intervals and modes** (seconds):

| Variable | Default | Purpose |
|----------|---------|---------|
| `VESTNIK_INTERVAL_SECONDS` | `3600` | UVO Vestník extraction interval |
| `CRZ_INTERVAL_SECONDS` | `3600` | CRZ extraction interval |
| `TED_INTERVAL_SECONDS` | `21600` | TED extraction interval (6 hours) |
| `ITMS_INTERVAL_SECONDS` | `3600` | ITMS extraction interval |
| `VESTNIK_MODE` | `recent` | `recent` or `historical` |
| `CRZ_MODE` / `TED_MODE` / `ITMS_MODE` | `recent` | Extraction mode for each source |

**Workers — stream and ingestor reliability:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `INGESTOR_BATCH_SIZE` | `100` | Messages per XREADGROUP call |
| `INGESTOR_MAX_DELIVERIES` | `5` | Deliveries before a failing entry is dead-lettered to `notices:dead` |
| `INGESTOR_RECLAIM_INTERVAL_SECONDS` | `30` | How often stale pending entries are reclaimed |
| `INGESTOR_RECLAIM_MIN_IDLE_MS` | `60000` | Idle time before a pending entry is reclaimable |
| `INGESTOR_MAINTENANCE_INTERVAL_SECONDS` | `30` | Cadence for MINID trimming and lag and PEL metrics |
| `STREAM_MAXLEN_APPROX` | `1000000` | Memory safety cap per stream. Acked entries are trimmed separately |
| `STREAM_HIGH_WATER` | `50000` | Extractors pause while consumer-group lag + pending reaches this |
| `CHECKPOINT_OVERLAP_SECONDS` | `86400` | CRZ/TED re-fetch window behind the cycle start |

**Workers — cross-source deduplication:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEDUP_INTERVAL_SECONDS` | `3600` | Fallback poll interval (1 hour) |
| `DEDUP_DEBOUNCE_SECONDS` | `5` | Coalesce `notices:written` events within N seconds |
| `DEDUP_WINDOW_DAYS` | `30` | Only dedup notices ingested in the last N days |
| `DEDUP_LOCK_TTL_SECONDS` | `1800` | TTL of the cross-replica `dedup:lock` |

**Workers — ITMS cache:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `ITMS_CACHE_BACKEND` | `redis` | `redis` (production) or `memory` (tests) |
| `ITMS_CACHE_TTL_SECONDS` | `604800` | Cache TTL (7 days) |

**Legacy pipeline** (one-shot backfill mode):

| Variable | Default | Purpose |
|----------|---------|---------|
| `HISTORICAL_FROM_YEAR` | `2014` | Start year for `pipeline run --mode historical` |
| `RECENT_DAYS` | `365` | Days window for `pipeline run --mode recent` |

**MCP and API data access:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `EKOSYSTEM_BASE_URL` | `https://datahub.ekosystem.slovensko.digital` | Ekosystem Datahub URL |
| `EKOSYSTEM_API_TOKEN` | `""` | Ekosystem API token (optional) |
| `TED_BASE_URL` | `https://api.ted.europa.eu` | TED API URL |
| `REQUEST_TIMEOUT` | `30.0` | HTTP request timeout (seconds) |
| `CACHE_TTL_SEARCH` | `300` | Declared on MCP `Settings` but **not read** by any cache. Search TTL is the constant in `adapters/mongo/procurements.py`. Setting it has no effect |
| `CACHE_TTL_ENTITY` | `3600` | Same as above. Entity search TTL is the constant in `adapters/mongo/subjects.py` |
| `CACHE_TTL_DETAIL` | `1800` | Same as above. Detail is uncached |

Per-cache TTLs and maxsizes are listed in [architecture/caching.md](architecture/caching.md).

**Monitoring** (only with `docker compose --profile monitoring`; see [`monitoring/README.md`](../monitoring/README.md)):

| Variable | Default | Purpose |
|----------|---------|---------|
| `GRAFANA_ADMIN_PASSWORD` | `uvo_grafana_dev` (dev-only default, read by `docker-compose.yml`) | Grafana `admin` password. Grafana listens on `127.0.0.1:3000` only. Set it in `.env` for anything beyond a laptop |
| `GIT_SHA` | `unknown` | Read by the API to set `uvo_build_info{git_sha}`. Not yet passed by `docker-compose.yml` or the Dockerfile, so local builds report `unknown` |

## Project Structure

```
uvo-search/
├── src/
│   ├── uvo_core/                         # Shared core; imports no other package
│   │   ├── services/                     # Query services used by API and MCP (search, graph, risk, analytics)
│   │   ├── domain/                       # Models, CPV helpers, scoring, hashing, company merge
│   │   ├── adapters/mongo/               # Loaders, dedup, ingestion log, checkpoints, search indexes
│   │   ├── adapters/neo4j/               # Graph queries and loader
│   │   ├── adapters/redis/               # Streams, locks, pub/sub, cache invalidation, client
│   │   ├── infra/clients.py              # Client factories with explicit timeouts and pools
│   │   ├── cache.py, errors.py, ports.py
│   │   └── testing.py
│   │
│   ├── uvo_api/                          # FastAPI delivery adapter (port 8001)
│   │   ├── app.py, config.py, auth.py, ratelimit.py, errors.py, v1_errors.py
│   │   ├── routers/                      # /api/* routers; routers/v1/ for the public API
│   │   └── __main__.py
│   │
│   ├── uvo_mcp/                          # FastMCP delivery adapter (port 8000)
│   │   ├── server.py, config.py, __main__.py
│   │   └── tools/                        # procurements, subjects, graph, risk, autocomplete, vector_search
│   │
│   ├── uvo_pipeline/                     # Source extractors/transformers, health CLI, legacy orchestrator
│   │   ├── extractors/                   # vestnik_nkod, crz, ted, itms
│   │   ├── transformers/                 # Normalize to CanonicalNotice
│   │   ├── catalog/nkod.py               # Vestník dataset discovery (NKOD SPARQL)
│   │   ├── cache/                        # ITMS cache backends (memory, redis)
│   │   ├── utils/                        # date validation, fetch_with_retry, rate limiter
│   │   ├── health.py, orchestrator.py, config.py
│   │   └── __main__.py                   # uv run python -m uvo_pipeline [run|health]
│   │
│   ├── uvo_workers/                      # Long-lived ingestion services (ports 8091–8096)
│   │   ├── context.py, clients.py, settings.py, extract.py, runner.py
│   │   ├── vestnik.py, crz.py, ted.py, itms.py   # Source declarations
│   │   ├── ingestor.py, dedup.py
│   │   └── metrics.py, health.py
│   │
│   └── uvo-gui-react/                    # React 18 SPA (port 8080 / 5174 dev)
│       └── src/ (api, components, hooks, i18n, pages, lib, test)
│
├── tests/
│   ├── conftest.py
│   ├── core/, api/, mcp/, workers/, pipeline/, gui/   # Unit tests
│   ├── e2e/                              # End-to-end (requires docker compose)
│   └── test_dockerfiles.py
│
├── docs/
│   ├── architecture.md                   # System design and data flow
│   ├── backend.md                        # Backend (API, MCP, shared core)
│   ├── data-pipeline.md                  # Workers and pipeline operations
│   ├── reference.md                      # Quick reference (this file)
│   ├── api-v1.md                         # Public /v1 API
│   ├── plans/                            # Dated plans (historical)
│   └── superpowers/specs/                # Design specs (historical)
│
├── .github/workflows/
│   ├── ci.yml                            # test, lint (incl. lint-imports), frontend, images, compose E2E
│   └── docker-publish.yml                # Publish images after CI succeeds on main
│
├── Dockerfile                            # Multi-stage: targets mcp, api, workers, pipeline
├── docker-compose.yml                    # Local deployment
├── pyproject.toml                        # Dependencies, pytest, ruff, import-linter config
├── uv.lock                               # Locked dependency versions
├── .env.example                          # Configuration template
├── CLAUDE.md                             # Development context (what is live)
├── README.md                             # Project overview
└── .gitignore
```

## Dev Commands

### Setup

```bash
# Install dependencies
uv sync --all-extras

# Copy configuration
cp .env.example .env
# Edit .env and set MONGO_PASSWORD, NEO4J_PASSWORD
```

### Run Local

```bash
# Terminal 1: MCP server (streamable-http on 8000)
uv run python -m uvo_mcp

# Terminal 2: API (port 8001)
uv run python -m uvo_api

# Terminal 3: React SPA (Vite dev server)
cd src/uvo-gui-react && npm install && npm run dev

# Open http://localhost:5174
```

### Test

```bash
# Full unit suite (CI runs this with -m "not e2e and not integration")
uv run pytest tests/ --ignore=tests/e2e -q

# One area
uv run pytest tests/mcp/ -v

# E2E (requires docker compose up)
uv run pytest tests/e2e/ -v

# With coverage
uv run pytest --cov=src -v

# React SPA
cd src/uvo-gui-react && npm test -- --run
```

### Lint & Format

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/   # use `ruff format` without --check to rewrite
uv run lint-imports                      # layering contracts from pyproject.toml

cd src/uvo-gui-react && npm run lint && npx tsc -b
```

### Docker

```bash
# Build images
docker compose build

# Start services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down -v
```

See `CLAUDE.md` for the WSL-specific commands on this machine.

## Common Patterns

### Call the API from a frontend

The React SPA calls REST endpoints under `/api/`. It does not call the MCP server directly. Example (TanStack Query in React):

```ts
import { useQuery } from "@tanstack/react-query";

export function useContracts(q: string) {
  return useQuery({
    queryKey: ["contracts", q],
    queryFn: async () => {
      const r = await fetch(`/api/contracts?q=${encodeURIComponent(q)}`);
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    },
  });
}
```

The API router validates the parameters and calls `uvo_core.services.search` in-process. The MCP server exposes the same service functions as tools for LLM clients.

## URLs & External Resources

| Resource | Link |
|----------|------|
| **UVO Vestník** | https://www.uvo.gov.sk/vestnik |
| **NKOD (data.gov.sk)** | https://data.gov.sk |
| **ITMS Open Data** | https://www.itms2014.sk/ |
| **FastMCP** | https://github.com/anthropics/mcp-py-server |
| **TED API** | https://ted.europa.eu/api |
| **Ekosystem Datahub** | https://datahub.ekosystem.slovensko.digital |

## Dependencies

Runtime dependencies are declared in `pyproject.toml`. The main ones are:

- `mcp[cli]` — Model Context Protocol server (FastMCP)
- `fastapi[standard]`, `uvicorn` — API
- `motor`, `neo4j`, `redis` — database and cache clients
- `fastembed` — local embeddings for vector search
- `pydantic`, `pydantic-settings` — validation and configuration
- `cachetools` — in-process caches
- `lxml` — Vestník XML parsing

Development dependencies include `pytest` (with `pytest-asyncio`, `pytest-cov`, `respx`, `fakeredis`, `mongomock-motor`), `ruff`, and `import-linter`.

## Configuration Files

| File | Purpose |
|------|---------|
| `.env.example` | Configuration template (copy to `.env`) |
| `.env` | Active configuration (not in git) |
| `pyproject.toml` | Project metadata, dependencies, pytest config, ruff config |
| `CLAUDE.md` | Development context and gotchas |
| `docker-compose.yml` | Local deployment configuration |
| `.github/workflows/ci.yml` | CI/CD pipeline (tests, lint, Docker build) |

## Error Shapes

### API

| Condition | Response |
|-----------|----------|
| Validation error | 422 from FastAPI |
| Backend unavailable (`BackendUnavailable`) | 503 with a generic detail; the reason is logged, not returned |
| Graph route with `API_NEO4J_URI` unset | 503 |
| Ops endpoint, `API_OPS_TOKEN` empty | 503 (endpoints are unconfigured and refuse all callers) |
| Ops endpoint, missing or wrong bearer token | 401 |

### MCP tools

| Condition | Response |
|-----------|----------|
| MongoDB not configured | `{"error": "MongoDB not configured", "status_code": 503}` |
| Procurement not found | `{"error": "Procurement {id} not found", "status_code": 404}` |
| Backend exception | Reported by FastMCP as a tool error |

### Frontend Error Messages

| Message | Cause | Recovery |
|---------|-------|----------|
| "Chyba pri vyhľadávaní: ..." | API request failed | Retry search |
| "Hľadať" button disabled | Loading in progress | Wait for completion |
| Empty results | No matches found | Broaden search criteria |

## Performance Considerations

- **Page size**: default 20, max 100 (`clamp_page`). Offsets are capped as well.
- **Request timeout**: 30 seconds (`REQUEST_TIMEOUT` for MCP)
- **Client bounds**: explicit timeouts and pool sizes come from `uvo_core.infra.clients`, configured per service
- **Caching**: in-process TTL caches for search (`CACHE_TTL_SEARCH`), entity lookups (`CACHE_TTL_ENTITY`), and detail views (`CACHE_TTL_DETAIL`). Dashboard aggregates are cached too. A `notices:written` subscriber clears them.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for:
- Code style (ruff)
- Testing requirements
- Git workflow
- PR process
