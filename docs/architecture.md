# UVO Search Architecture

## Overview

UVO Search is a **three-tier Python application** designed to search and browse Slovak government procurement data:

1. **MCP Server** (port 8000) — FastMCP providing tools for data access
2. **API Bridge** (port 8001) — FastAPI wrapping MCP tools with HTTP endpoints
3. **Frontends** — React SPA (public) + Vue dashboard (admin) + Claude integration
4. **Data sources** — Pipeline ingests from UVO Vestník (XML), CRZ (Ekosystem), ITMS, TED and NKOD

The system allows multiple clients to share a single data backend.

## System Architecture

```
┌──────────────────────────────────────────────┐
│  MCP Server (port 8000, FastMCP + Python)   │
│  ├─ 6 tools (search, graph, entities, etc.)  │
│  ├─ TTL caching via cachetools              │
│  ├─ Health check (/health)                  │
│  └─ stdio transport (Claude Desktop/Code)   │
└──────────────────────────────────────────────┘
    ↑                      ↑
  (HTTP)                (stdio)
    │                      │
    ├─────────────────────────────────┐
    │                                 │
┌───┴──────────────────────┐    ┌────┴────────┐
│ API Bridge               │    │   Claude    │
│ (port 8001, FastAPI)     │    │ Desktop/Code│
└───┬──────────────────────┘    └─────────────┘
    ├──────────────────┬──────────────────┐
    │                  │                  │
┌───┴────────────┐ ┌──┴──────────┐
│ React SPA      │ │ Vue Admin   │
│ (port 8080)    │ │ (port 5173) │
│ Vite+React+TS  │ │ Vue 3+TS    │
├────────────────┤ ├─────────────┤
│ • Search       │ │ • Dashboard │
│ • Procurers    │ │ • Contracts │
│ • Suppliers    │ │ • Analytics │
│ • Graphs       │ │ • Dark theme│
│ • CPV trends   │ │ • Hotkeys   │
└────────────────┘ └─────────────┘

External Data Sources:
├─ UVO Vestník (Slovak procurement notices, XML)
├─ Ekosystem Datahub (CRZ contracts)
├─ ITMS (EU structural funds)
├─ TED API (EU procurements)
└─ NKOD (national open data catalog, DCAT/CKAN)
```

## Process Architecture

### React SPA Frontend (port 8080, primary)

- **Framework**: Vite 5 + React 18 + TypeScript
- **Language**: TypeScript + React hooks
- **Features**:
  - Client-side routing (React Router 6)
  - URL-as-state (pagination, filters in query params)
  - Interactive search, filtering, sorting
  - TanStack Query for data fetching & caching
  - Network graph visualization (Cytoscape.js, lazy-loaded)
  - CPV trends and concentration analysis

- **Key Responsibilities**:
  - Single-page application with client-side navigation
  - Handle user interactions (search, pagination, filtering)
  - Call API backend via TanStack Query
  - Display results with Tailwind CSS + shadcn/ui components
  - Lazy-load large libraries (Cytoscape)

**Port**: 8080 (Docker host) / 5174 (dev)

**Bind Host**: `0.0.0.0` (configurable in Dockerfile)

### FastAPI Bridge (port 8001)

- **Framework**: FastAPI (Python)
- **Language**: Python
- **Features**:
  - Routes requests from frontends to MCP server
  - Wraps MCP tools with HTTP endpoints (GET, POST)
  - Adds new endpoints for React GUI requirements (graph, dashboard, concentration)
  - CORS-enabled for browser requests
- **Key Responsibilities**:
  - Accept HTTP requests from React SPA and Vue dashboard
  - Call MCP server tools
  - Return JSON responses
  - Cache decorator support (future)

**Port**: 8001

**Bind Host**: `0.0.0.0`

### Vue Admin GUI (port 5173)

- **Framework**: Vue 3 + TypeScript + Pinia (state management)
- **Styling**: Tailwind CSS v4 + dark mode
- **Features**:
  - Grafana-style layout (Sidebar + TopBar + Panels)
  - Dark/light theme with localStorage persistence
  - Command palette (⌘K) for quick navigation
  - Hotkey support (Cmd/Ctrl combinations)
  - Responsive data tables with sorting/pagination
  - Chart.js visualizations (spend, CPV breakdown)
  - Filter store for global filtering state

**Key Responsibilities**:
- Render analytics dashboard and admin views
- Manage theme state (dark/light) and persist to localStorage
- Handle command palette and hotkeys
- Call MCP server tools via fetch
- Display charts and data tables with Tailwind styling

**Port**: 5173 (dev) / 4173 (preview)
**Build Host**: `0.0.0.0` (configurable in vite.config.ts)

### FastMCP Server (port 8000)

- **Framework**: FastMCP (Anthropic's MCP server library)
- **Language**: Python
- **Features**:
  - Stateless tool execution
  - Shared httpx AsyncClient for API calls
  - Error handling and HTTP status mapping
  - Health check endpoint (`/health`)
  - Streamable-HTTP transport for GUI + stdio for Claude Desktop/Code

**Key Responsibilities**:
- Execute MCP tools (search, detail lookup, entity search)
- Query MongoDB (Atlas Search) and Neo4j for pre-ingested data
- Return structured JSON responses
- Handle errors and timeouts gracefully

**Port**: 8000
**Bind Host**: `0.0.0.0` (configurable via `MCP_HOST`)
**Health Endpoint**: `GET /health` — returns `{"status": "ok", "service": "uvo-mcp"}`

## Communication Flow

### Browser → React SPA → API Bridge → MCP Server

1. User enters search query and clicks search
2. React component calls `api.search({...})` via TanStack Query
3. Query sends GET request to `http://localhost:8001/contracts?query=...`
4. API bridge receives request, validates params
5. API bridge calls MCP server tool: `search_completed_procurements(...)`
6. MCP server receives tool call, validates arguments
7. MCP server queries MongoDB (Atlas Search) / Neo4j
8. Storage returns matched documents / subgraphs
9. MCP server returns result to API bridge
10. API bridge wraps result in JSON and returns to React
11. React component (via TanStack Query) parses result, updates cache
12. Component re-renders with new data

**New API Endpoints** (added in React redesign):

- `GET /dashboard/by-month?year=YYYY` — monthly aggregation
- `GET /dashboard/by-cpv?year_from=Y&year_to=Y` — CPV trends
- `GET /dashboard/ingestion` — pipeline health snapshot (source status, 30-day ingestion trends, dedup metrics)
- `GET /graph/ego/{ico}?hops=N` — entity ego network
- `GET /graph/cpv/{cpv}?year=YYYY` — CPV network
- `GET /procurers/{ico}/concentration?top_n=N` — HHI supplier concentration
- `GET /contracts?procurer_ico=ICO` — contracts by procurer (new filter param)

### Claude Desktop/Code → MCP Server (stdio)

1. User references MCP server in Claude config (via stdio)
2. Claude starts MCP server process with `python -m uvo_mcp stdio`
3. Claude sends tool calls over stdin
4. MCP server processes stdin, executes tool
5. MCP server returns result to stdout
6. Claude parses output and uses in response

## Key Design Decisions

### Why Two Processes?

1. **Independent Scaling** — MCP server handles API calls and caching; GUI handles WebSocket connections independently.
2. **Independent Deployment** — Update frontend without restarting data layer; scale each separately.
3. **Multiple Clients** — Claude Desktop/Code connect via stdio; GUI connects via HTTP; same backend serves both.
4. **Simpler Debugging** — Isolate data layer issues from UI issues; test tools independently.
5. **Separation of Concerns** — Frontend logic (pagination, UI state) separate from data fetching (API calls, caching).

### Why MCP?

- **Tool Standardization** — Claude Desktop/Code can access the same tools as the web GUI.
- **Future-Proof** — MCP is the standard for AI tool integration; easy to add new clients later.
- **Framework Agnostic** — Frontend can be rebuilt in any framework without touching the data layer.

## Data Flow: Search Example

**User enters "stavebnictvom" and clicks search:**

```
React SPA (Search page, TanStack Query)
  ↓
[useQuery -> api.search({...})]
  └─ GET http://localhost:8001/contracts?query=...
      ↓
[FastAPI bridge]
  └─ Call MCP tool: "search_completed_procurements"
      ↓
[MCP Server: search_completed_procurements()]
  ├─ Validate arguments (limit <= max_page_size, offset >= 0)
  ├─ Build Atlas Search compound query (sk_folding analyzer)
  └─ Execute MongoDB aggregation on `notices` collection
      ↓
[MongoDB Atlas Local]
  └─ Returns: matched notices + total count
      ↓
[MCP Server -> API bridge -> JSON response]
      ↓
[React: TanStack Query updates cache]
  └─ Component re-renders results + pagination
```

## Configuration & Environment

All settings are environment variables (loaded from `.env`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `MONGO_PASSWORD` | *(required)* | Password for MongoDB |
| `NEO4J_PASSWORD` | *(required)* | Password for Neo4j |
| `MCP_HOST` | `0.0.0.0` | MCP server bind address |
| `MCP_PORT` | `8000` | MCP server port |
| `MCP_SERVER_URL` | `http://localhost:8000/mcp` | URL frontend uses to reach MCP server |
| `EKOSYSTEM_BASE_URL` | `https://datahub.ekosystem.slovensko.digital` | Ekosystem Datahub URL |
| `EKOSYSTEM_API_TOKEN` | *(optional)* | Token for Ekosystem (not required for public endpoints) |
| `REQUEST_TIMEOUT` | `30.0` | HTTP request timeout in seconds |
| `CACHE_TTL_SEARCH` | `300` | Search result cache TTL (seconds) |
| `CACHE_TTL_ENTITY` | `3600` | Entity lookup cache TTL (seconds) |
| `CACHE_TTL_DETAIL` | `1800` | Detail view cache TTL (seconds) |

**Note**: Caching is currently a configuration layer but not yet implemented in tools.

## Deployment

### Local Development

**Terminal 1 — MCP Server**:
```bash
uv run python -m uvo_mcp
```

**Terminal 2 — API bridge**:
```bash
uv run python -m uvo_api
```

**Terminal 3 — React GUI**:
```bash
cd src/uvo-gui-react && npm run dev
```

The React SPA reaches the API bridge on port 8001 (and indirectly the MCP server on 8000).

### Docker Compose

```bash
docker compose up -d --build
```

Services:
- `mcp-server` (port 8000) — Fast boot, health check every 10s
- `api` (port 8001) — FastAPI bridge
- `gui-react` (port 8080) — Waits for mcp-server to be healthy before starting

### Kubernetes (Future)

The two services can be deployed as separate pods with:
- `mcp-server` pod — Stateless, horizontally scalable
- `gui` pod — Stateless, horizontally scalable
- ConfigMap for environment variables
- Service discovery for inter-pod communication

## Monitoring & Observability

### Health Checks

- **MCP Server**: `GET http://localhost:8000/health` → `{"status": "ok", "service": "uvo-mcp"}`
- **React GUI**: `GET http://localhost:8080/` → HTTP 200 (nginx-served static SPA)

### Logging

All loggers use Python's `logging` module. Set `LOG_LEVEL` env var:
- `DEBUG` — Detailed tool execution, API calls, state changes
- `INFO` — Normal operation (default)
- `WARNING` — Rate limits, slow requests
- `ERROR` — API failures, connection errors

### Error Handling

**Frontend** (graceful degradation):
- API timeout → display error message, allow retry
- API 429 (rate limited) → cached results if available
- Malformed response → "Chyba pri vyhľadávaní: {exception}"

**MCP Server**:
- HTTP 5xx → return error dict with status code
- Connection timeout → return error dict
- Validation errors → return 400 (handled by FastMCP)

## Data Pipeline

A separate **pipeline service** ingests from five sources into MongoDB + Neo4j:

```
NKOD (CKAN)   UVO Vestník   Ekosystem/CRZ   ITMS         TED
  │             (XML)         │               │           API
  │             │             │               │           │
  └─────────────┼─────────────┼───────────────┼───────────┘
                │
         Pipeline Container
         ├─ extractors/ (uvo, crz, itms, ted, vestnik_xml, vestnik_nkod)
         ├─ catalog/ (ckan, nkod) — source discovery
         ├─ transformers/ → CanonicalNotice
         ├─ Cross-source deduplication
         └─ Load to MongoDB + Neo4j
                │
         ┌──────┴──────┐
         │             │
      MongoDB       Neo4j
      (notices)     (graph)
         │             │
         └──────┬──────┘
                │
           MCP Server
         (reads via queries)
```

**Modes**:
- `recent` (default) — Last 365 days, checkpoint-based incremental
- `historical` — Full backfill (one-time)
- `dry-run` — Validate config without DB writes

**Deduplication**:
- Per-source: `(source, source_id)` unique constraint
- Cross-source: Hash matching on `(procurer_ico, cpv_code)` links notices

See [data-pipeline.md](data-pipeline.md) for details.
