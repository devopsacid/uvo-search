# Reference Guide

Quick lookup reference for developers.

## MCP Tool Signatures

All tools return JSON dicts. Error responses include `error` and `status_code` fields.

### search_completed_procurements

```
Name:       search_completed_procurements
Module:     uvo_mcp.tools.procurements
Endpoint:   POST /mcp (via MCP protocol)

Parameters:
  text_query (str, optional)    Full-text search query
  cpv_codes (list[str], optional) EU product classification codes
  procurer_id (str, optional)   Filter by authority ID
  supplier_ico (str, optional)  Filter by supplier company number
  date_from (str, optional)     Start date (YYYY-MM-DD)
  date_to (str, optional)       End date (YYYY-MM-DD)
  limit (int, default 20)       Page size (max 100)
  offset (int, default 0)       Result offset

Returns:
  {
    "data": [
      {
        "id": str,
        "nazov": str,
        "konecna_hodnota": float,
        "datum_zverejnenia": str,
        "obstaravatel_nazov": str,
        "cpv_kod": str,
        "stav": str,
        "dodavatelia": [{"nazov": str, "ico": str}],
        ...
      }
    ],
    "total": int
  }
```

### get_procurement_detail

```
Name:       get_procurement_detail
Module:     uvo_mcp.tools.procurements
Endpoint:   POST /mcp (via MCP protocol)

Parameters:
  procurement_id (str, required) Procurement ID

Returns:
  {
    "id": str,
    "nazov": str,
    "konecna_hodnota": float,
    "datum_zverejnenia": str,
    "obstaravatel_nazov": str,
    "cpv_kod": str,
    "stav": str,
    "dodavatelia": [{"nazov": str, "ico": str}],
    "popis": str,
    ...
  }

Error (404):
  {"error": "Procurement {id} not found", "status_code": 404}
```

### find_procurer

```
Name:       find_procurer
Module:     uvo_mcp.tools.subjects
Endpoint:   POST /mcp (via MCP protocol)

Parameters:
  name_query (str, optional)    Full-text search by name
  ico (str, optional)           Company registration number
  limit (int, default 20)       Page size (max 100)
  offset (int, default 0)       Result offset

Returns:
  {
    "data": [
      {
        "id": str,
        "nazov": str,
        "ico": str,
        "zakazky_count": int,
        "total_value": float,
        ...
      }
    ],
    "total": int
  }
```

### find_supplier

```
Name:       find_supplier
Module:     uvo_mcp.tools.subjects
Endpoint:   POST /mcp (via MCP protocol)

Parameters:
  name_query (str, optional)    Full-text search by name
  ico (str, optional)           Company registration number
  limit (int, default 20)       Page size (max 100)
  offset (int, default 0)       Result offset

Returns:
  {
    "data": [
      {
        "id": str,
        "nazov": str,
        "ico": str,
        "zakazky_count": int,
        "total_value": float,
        ...
      }
    ],
    "total": int
  }
```

## Frontends

The public SPA lives in [`src/uvo-gui-react/`](../src/uvo-gui-react/) (React 18 + Vite + TanStack Query). It calls the FastAPI bridge on port 8001, which fans out to the MCP server. See the package's `README.md` for routes, components, and dev instructions.

## Environment Variables

**Storage** (required):
| Variable | Default | Purpose |
|----------|---------|---------|
| `MONGO_PASSWORD` | — | MongoDB user password |
| `NEO4J_PASSWORD` | — | Neo4j user password |

**Redis** (required for microservices):
| Variable | Default | Purpose |
|----------|---------|---------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URI |
| `REDIS_PASSWORD` | `` | Redis password (if auth enabled) |

**Microservices — Extractor Intervals** (all in seconds):
| Variable | Default | Purpose |
|----------|---------|---------|
| `VESTNIK_INTERVAL_SECONDS` | `3600` | UVO Vestník extraction interval |
| `CRZ_INTERVAL_SECONDS` | `3600` | CRZ extraction interval |
| `TED_INTERVAL_SECONDS` | `21600` | TED extraction interval (6 hours) |
| `ITMS_INTERVAL_SECONDS` | `3600` | ITMS extraction interval |

**Microservices — Extraction Modes**:
| Variable | Default | Purpose |
|----------|---------|---------|
| `VESTNIK_MODE` | `recent` | `recent` or `historical` (legacy pipeline modes) |
| `CRZ_MODE` | `recent` | `` |
| `TED_MODE` | `recent` | `` |
| `ITMS_MODE` | `recent` | `` |

**Microservices — Cross-source Deduplication**:
| Variable | Default | Purpose |
|----------|---------|---------|
| `DEDUP_INTERVAL_SECONDS` | `3600` | Fallback poll interval (1 hour) |
| `DEDUP_DEBOUNCE_SECONDS` | `5` | Coalesce events within N seconds |
| `DEDUP_WINDOW_DAYS` | `30` | Only dedup notices ingested in last N days |

**Microservices — ITMS Cache** (Redis-backed by default):
| Variable | Default | Purpose |
|----------|---------|---------|
| `ITMS_CACHE_BACKEND` | `redis` | `redis` (production) or `memory` (tests) |
| `ITMS_CACHE_TTL_SECONDS` | `604800` | Cache TTL (7 days) |

**Microservices — Ingestor Batching**:
| Variable | Default | Purpose |
|----------|---------|---------|
| `INGESTOR_BATCH_SIZE` | `100` | Messages per XREADGROUP call |
| `STREAM_MAXLEN_APPROX` | `100000` | Approximate max entries per Redis stream |

**Legacy Pipeline** (one-shot backfill mode):
| Variable | Default | Purpose |
|----------|---------|---------|
| `HISTORICAL_FROM_YEAR` | `2014` | Start year for `pipeline run --mode historical` |
| `RECENT_DAYS` | `365` | Days window for `pipeline run --mode recent` |

**MCP Server** (data layer):
| Variable | Default | Purpose |
|----------|---------|---------|
| `EKOSYSTEM_BASE_URL` | `https://datahub.ekosystem.slovensko.digital` | Ekosystem Datahub URL |
| `EKOSYSTEM_API_TOKEN` | `` | Ekosystem API token (optional) |
| `TED_BASE_URL` | `https://api.ted.europa.eu` | TED API URL |
| `MCP_SERVER_URL` | `http://localhost:8000/mcp` | URL for API bridge to reach MCP server |
| `MCP_HOST` | `0.0.0.0` | MCP server bind address |
| `MCP_PORT` | `8000` | MCP server port |
| `CACHE_TTL_SEARCH` | `300` | Search result cache TTL (seconds) |
| `CACHE_TTL_ENTITY` | `3600` | Entity lookup cache TTL (seconds) |
| `CACHE_TTL_DETAIL` | `1800` | Detail view cache TTL (seconds) |
| `REQUEST_TIMEOUT` | `30.0` | HTTP request timeout (seconds) |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Project Structure

```
uvo-search/
├── src/
│   ├── uvo_mcp/                          # MCP server (port 8000)
│   │   ├── __main__.py, server.py, config.py, models.py
│   │   └── tools/ (procurements.py, subjects.py, graph.py)
│   │
│   ├── uvo_api/                          # FastAPI bridge (port 8001)
│   │   └── routers/ (contracts.py, dashboard.py, graph.py, procurers.py, suppliers.py)
│   │
│   ├── uvo_pipeline/                     # Shared library (no public port)
│   │   ├── extractors/                   # Source-specific extraction (vestnik, crz, ted, itms)
│   │   ├── transformers/                 # Normalize to CanonicalNotice
│   │   ├── loaders/                      # Mongo + Neo4j loading
│   │   ├── redis_client.py               # Async Redis factory (NEW)
│   │   ├── streams.py                    # XADD, XREADGROUP, XACK helpers (NEW)
│   │   ├── pubsub.py                     # PUBLISH, SUBSCRIBE helpers (NEW)
│   │   ├── locks.py                      # Distributed lock CAS helpers (NEW)
│   │   ├── dedup.py                      # Cross-source dedup (moved from orchestrator) (NEW)
│   │   ├── cache/                        # ITMS cache backends (NEW)
│   │   │   ├── memory.py                 # In-process (tests)
│   │   │   └── redis.py                  # Redis-backed (production)
│   │   ├── orchestrator.py               # Legacy one-shot entry point
│   │   ├── models.py, config.py
│   │   └── __main__.py                   # Legacy CLI: uv run python -m uvo_pipeline
│   │
│   ├── uvo_workers/                      # Long-lived microservice daemons (NEW)
│   │   ├── runner.py                     # Daemon loop, signal handling, /health, lock
│   │   ├── vestnik.py, crz.py, ted.py, itms.py  # Per-source extractors
│   │   ├── ingestor.py                   # Streams consumer
│   │   ├── dedup.py                      # Dedup subscriber
│   │   ├── health.py                     # /health endpoint helpers
│   │   └── __main__.py                   # Entry point: uv run python -m uvo_workers.<service>
│   │
│   └── uvo-gui-react/                    # React 18 SPA (port 8080 / 5174 dev)
│       └── src/ (components, hooks, pages, i18n, lib)
│
├── tests/
│   ├── conftest.py                       # Shared pytest fixtures
│   ├── mcp/                              # MCP unit tests (mocked)
│   ├── api/                              # API bridge unit tests
│   ├── pipeline/                         # Pipeline unit tests
│   └── e2e/                              # End-to-end (requires docker compose)
│
├── docs/
│   ├── architecture.md                   # System design and data flow
│   ├── backend.md                        # Backend (MCP + microservices) guide
│   ├── data-pipeline.md                  # Data pipeline (microservices) operations
│   ├── reference.md                      # Quick reference (this file)
│   ├── plan.md                           # Project roadmap
│   ├── data-sources-research.md          # API documentation
│   └── superpowers/
│       └── specs/
│           └── 2026-04-27-source-microservices-design.md  # Authoritative design spec
│
├── .github/workflows/
│   ├── ci.yml                            # Unit tests, lint, Docker build
│   └── docker-publish.yml                # Push to registry on tag
│
├── Dockerfile.mcp                        # MCP server image
├── Dockerfile.api                        # API bridge image
├── docker-compose.yml                    # Local deployment (14 services)
├── pyproject.toml                        # Dependencies, tooling config
├── uv.lock                               # Locked dependency versions
├── .env.example                          # Configuration template
├── CLAUDE.md                             # Development context
├── README.md                             # Project overview
└── .gitignore
```

**New in source-microservices**:
- `src/uvo_workers/` — 6 daemon entrypoints (4 extractors + ingestor + dedup-worker)
- `src/uvo_pipeline/redis_client.py`, `streams.py`, `pubsub.py`, `locks.py` — Redis integration helpers
- `src/uvo_pipeline/cache/` — ITMS cache abstraction (memory + Redis backends)
- `src/uvo_pipeline/dedup.py` — Extracted from `orchestrator.py` for reuse
- `docs/superpowers/specs/2026-04-27-source-microservices-design.md` — Full design specification

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
# Terminal 1: MCP server
uv run python -m uvo_mcp

# Terminal 2: API bridge
uv run python -m uvo_api

# Terminal 3: React SPA (Vite dev server)
cd src/uvo-gui-react && npm install && npm run dev

# Open http://localhost:5174
```

### Run with Hot Reload

```bash
# MCP server (auto-restarts on code change)
uv run watchfiles 'python -m uvo_mcp' src/uvo_mcp

# React SPA (Vite HMR is the default `npm run dev`)
cd src/uvo-gui-react && npm run dev
```

### Test

```bash
# All Python unit tests
uv run pytest tests/mcp/ tests/api/ tests/pipeline/ -v

# MCP tests only
uv run pytest tests/mcp/ -v

# With coverage
uv run pytest tests/ -m "not e2e and not integration" --cov=src/

# Specific test
uv run pytest tests/mcp/test_procurements.py::test_search -v
```

### Lint & Format

```bash
# Check for issues
uv run ruff check src/ tests/

# Auto-fix
uv run ruff check --fix src/ tests/

# Format code
uv run ruff format src/ tests/
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

## Common Patterns

### Call an MCP Tool from a Frontend

The React SPA goes through the FastAPI bridge — it calls REST endpoints, not the MCP server directly. Example (TanStack Query in React):

```ts
import { useQuery } from "@tanstack/react-query";

export function useContracts(query: string) {
  return useQuery({
    queryKey: ["contracts", query],
    queryFn: async () => {
      const r = await fetch(`/api/contracts?query=${encodeURIComponent(query)}`);
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    },
  });
}
```

The API bridge translates that request into an MCP tool call (`search_completed_procurements`) and returns JSON.

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

**Runtime**:
- `mcp[cli]>=1.0.0` — Model Context Protocol (Anthropic)
- `httpx>=0.27.0` — Async HTTP client
- `pydantic>=2.0.0` — Data validation
- `pydantic-settings>=2.0.0` — Configuration management
- `cachetools>=5.0.0` — Caching utilities (future use)

**Development**:
- `pytest>=8.0` — Testing framework
- `pytest-asyncio>=0.24` — Async test support
- `pytest-cov>=5.0` — Coverage reporting
- `respx>=0.22` — HTTP mocking (tests)
- `ruff>=0.8` — Linter & formatter

## Configuration Files

| File | Purpose |
|------|---------|
| `.env.example` | Configuration template (copy to `.env`) |
| `.env` | Active configuration (not in git) |
| `pyproject.toml` | Project metadata, dependencies, pytest config, ruff config |
| `CLAUDE.md` | Development context and gotchas |
| `docker-compose.yml` | Local deployment configuration |
| `.github/workflows/ci.yml` | CI/CD pipeline (tests, lint, Docker build) |

## Error Codes

### HTTP Status Codes

| Code | Meaning | Handled By |
|------|---------|-----------|
| 200 | Success | Tool returns data |
| 400 | Bad request | Tool returns error dict |
| 404 | Not found | Tool returns error dict |
| 429 | Rate limited | Tool returns error dict (cache if available, future) |
| 5xx | Server error | Tool returns error dict |
| 0 | Connection error | Tool returns error dict |

### Frontend Error Messages

| Message | Cause | Recovery |
|---------|-------|----------|
| "Chyba pri vyhľadávaní: ..." | MCP tool failed | Retry search |
| "Hľadať" button disabled | Loading in progress | Wait for completion |
| Empty results | No matches found | Broaden search criteria |

## Performance Considerations

- **Page size**: Default 20, max 100 (configurable via MCP tool)
- **Request timeout**: 30 seconds (configurable via `REQUEST_TIMEOUT`)
- **Search caching**: Configured (300s) but not yet implemented
- **Entity caching**: Configured (3600s) but not yet implemented

See [plan.md](plan.md) for caching implementation roadmap.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for:
- Code style (ruff)
- Testing requirements
- Git workflow
- PR process
