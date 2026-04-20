# UVO Search Architecture

## Overview

UVO Search is a **two-process Python application** designed to search and browse Slovak government procurement data. The system comprises:

1. **NiceGUI Frontend** — Web interface for browsing and searching procurements
2. **FastMCP Server** — API layer providing structured tools for data access
3. **External APIs** — Integration with UVOstat, Ekosystem Datahub, and TED

The two processes communicate over HTTP using the **streamable-http MCP protocol**, allowing independent scaling, deployment, and multiple client types.

## System Architecture

```
┌────────────────────────────────────────────────────┐
│  MCP Server (port 8000, FastMCP + Python)         │
│  ├─ 4 MCP tools (search, detail, find, contracts) │
│  ├─ TTL caching via cachetools                    │
│  ├─ Health check endpoint (/health)               │
│  └─ Request validation & error handling           │
└────────────────────────────────────────────────────┘
       ↑                    ↑                    ↑
   (HTTP)             (HTTP)             (stdio)
       │                    │                    │
   ┌───┴─────────────┐ ┌────┴──────────┐  ┌─────┴──────┐
   │ NiceGUI         │ │ Vue Admin GUI │  │ Claude     │
   │ (port 8080)     │ │ (port 5173)   │  │ Desktop/   │
   │ Python/FastAPI  │ │ Vue 3+TS      │  │ Code       │
   ├─────────────────┤ ├───────────────┤  └────────────┘
   │ • Search        │ │ • Dashboard   │
   │ • Procurers     │ │ • Contracts   │
   │ • Suppliers     │ │ • Analytics   │
   │ • Detail views  │ │ • Dark theme  │
   │ • Graphs        │ │ • Command pal │
   └─────────────────┘ └───────────────┘

External Data Sources:
├─ UVOstat.sk API (Slovak procurements, 2014+)
├─ Vestník NKOD SPARQL (Slovak bulletin, 2016+)
├─ Ekosystem Datahub (CRZ contracts, 2011+)
├─ TED API (EU procurements)
└─ RPVS/OpenSanctions (Beneficial ownership)
```

## Process Architecture

### NiceGUI Frontend (port 8080)

- **Framework**: NiceGUI 3.9 (FastAPI + Vue/Quasar + Tailwind CSS)
- **Language**: Python
- **Features**:
  - Fully Slovak-language UI
  - Server-side pagination for result sets
  - Interactive search filters (text, date range, CPV codes)
  - Split-panel detail views
  - Entity browsing (procurers, suppliers)
  - Relationship network graph visualization

**Key Responsibilities**:
- Render pages and components
- Handle user interactions (search, pagination, selection)
- Call MCP server tools via HTTP
- Display results and details

**Port**: 8080
**Bind Host**: `0.0.0.0` (configurable via `GUI_HOST`)

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
- Call external APIs (UVOstat, Ekosystem, TED)
- Return structured JSON responses
- Handle errors and timeouts gracefully

**Port**: 8000
**Bind Host**: `0.0.0.0` (configurable via `MCP_HOST`)
**Health Endpoint**: `GET /health` — returns `{"status": "ok", "service": "uvo-mcp"}`

## Communication Flow

### Browser → Frontend → MCP Server

1. User enters search query and clicks "Hľadať" (Search)
2. Frontend component calls `mcp_client.call_tool("search_completed_procurements", {...})`
3. Client establishes HTTP connection to MCP server via streamable-http protocol
4. MCP server receives tool call, validates arguments
5. MCP server calls UVOstat API with httpx client
6. UVOstat API returns JSON response
7. MCP server wraps result in JSON and returns to frontend
8. Frontend parses result, updates state, triggers refresh
9. Component re-renders with new data

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

### Why NiceGUI?

- **Server-Side** — No separate frontend build; Python developer friendly.
- **Fast Development** — Reactive components, built-in UI library (Quasar).
- **Full Stack** — One language (Python) for backend and frontend.

## Data Flow: Search Example

**User enters "stavebnictvom" and clicks search:**

```
Frontend (search.py)
  ↓
[SearchState.search()] 
  ├─ Set loading = True
  ├─ Clear results
  └─ Call mcp_client.call_tool()
      ↓
[mcp_client.py: call_tool()]
  ├─ Create streamable-http connection to MCP server
  ├─ Initialize ClientSession
  └─ Call tool: "search_completed_procurements"
      ↓
[MCP Server: search_completed_procurements()]
  ├─ Validate arguments (limit <= max_page_size, offset >= 0)
  ├─ Build params dict for UVOstat API
  └─ Call: httpx GET /api/ukoncene_obstaravania?text=stavebnictvom&limit=20&offset=0
      ↓
[UVOstat API]
  └─ Returns: {"data": [...], "total": 1234, ...}
      ↓
[MCP Server: process response]
  ├─ Check HTTP status (200 OK)
  ├─ Parse JSON
  └─ Return raw response to client
      ↓
[mcp_client: parse result]
  └─ Extract content.text from result
      ↓
[Frontend: SearchState._fetch()]
  ├─ Parse JSON response
  ├─ Update results, total, page
  ├─ Set loading = False
  └─ Call list_view.refresh() + detail_view.refresh()
      ↓
[NiceGUI rendering]
  └─ Render updated UI with results and pagination
```

## Configuration & Environment

All settings are environment variables (loaded from `.env`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `UVOSTAT_API_TOKEN` | *(required)* | API token for UVOstat.sk |
| `STORAGE_SECRET` | *(required)* | Secret key for NiceGUI session storage |
| `GUI_HOST` | `0.0.0.0` | NiceGUI bind address |
| `GUI_PORT` | `8080` | NiceGUI port |
| `MCP_HOST` | `0.0.0.0` | MCP server bind address |
| `MCP_PORT` | `8000` | MCP server port |
| `MCP_SERVER_URL` | `http://localhost:8000/mcp` | URL frontend uses to reach MCP server |
| `UVOSTAT_BASE_URL` | `https://www.uvostat.sk` | UVOstat API base URL |
| `EKOSYSTEM_BASE_URL` | `https://datahub.ekosystem.slovensko.digital` | Ekosystem Datahub URL (unused in MVP) |
| `REQUEST_TIMEOUT` | `30.0` | HTTP request timeout in seconds |
| `CACHE_TTL_SEARCH` | `300` | Search result cache TTL (seconds) |
| `CACHE_TTL_ENTITY` | `3600` | Entity lookup cache TTL (seconds) |
| `CACHE_TTL_DETAIL` | `1800` | Detail view cache TTL (seconds) |

**Note**: Caching is currently a configuration layer but not yet implemented in tools. See [plan.md](plan.md).

## Deployment

### Local Development

**Terminal 1 — MCP Server**:
```bash
uv run python -m uvo_mcp
```

**Terminal 2 — GUI**:
```bash
uv run python -m uvo_gui
```

The GUI connects to `http://localhost:8000/mcp` by default.

### Docker Compose

```bash
docker compose up -d --build
```

Services:
- `mcp-server` (port 8000) — Fast boot, health check every 10s
- `gui` (port 8080) — Waits for mcp-server to be healthy before starting

### Kubernetes (Future)

The two services can be deployed as separate pods with:
- `mcp-server` pod — Stateless, horizontally scalable
- `gui` pod — Stateless, horizontally scalable
- ConfigMap for environment variables
- Service discovery for inter-pod communication

## Monitoring & Observability

### Health Checks

- **MCP Server**: `GET http://localhost:8000/health` → `{"status": "ok", "service": "uvo-mcp"}`
- **GUI**: `GET http://localhost:8080/` → HTTP 200

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

A separate **pipeline service** ingests from four sources into MongoDB + Neo4j:

```
SPARQL        UVOstat       Ekosystem      TED
(NKOD)        API           Datahub        API
  │             │             │             │
  └─────────────┼─────────────┼─────────────┘
                │
         Pipeline Container
         ├─ discover_vestnik_datasets() — SPARQL catalog
         ├─ fetch_bulletin() — Download + parse Vestník JSON
         ├─ transform_* → CanonicalNotice
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
- `historical` — Full backfill from 2014/2016 (one-time)
- `dry-run` — Validate config without DB writes

**Deduplication**:
- Per-source: `(source, source_id)` unique constraint
- Cross-source: Hash matching on `(procurer_ico, cpv_code)` links notices

See [data-pipeline.md](data-pipeline.md) and [plan-vestnik-nkod.md](plan-vestnik-nkod.md) for details.

## Future Enhancements

See [plan.md](plan.md) for:
- Additional MCP tools (announced procurements, entity profiles)
- Multi-lot support in Vestník extractor
- Performance optimizations (pagination benchmarks, query optimization)
- Beneficial ownership integration and compliance analysis
