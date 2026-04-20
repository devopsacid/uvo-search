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

## Frontend Routes

| Route | Page Function | State Class | Purpose |
|-------|---------------|-------------|---------|
| `/` | `search_page()` | `SearchState` | Main search with split-panel (left: results, right: detail) |
| `/procurers` | `procurers_page()` | `ProcurersState` | Browse contracting authorities (3-column grid) |
| `/suppliers` | `suppliers_page()` | `SuppliersState` | Browse suppliers (3-column grid) |
| `/about` | `about_page()` | None | Information page with data source attribution |

## Frontend Components

### layout(current_path: str)

**File**: `src/uvo_gui/components/layout.py`

Context manager providing header + sidebar + page container.

```python
@ui.page("/my-page")
async def my_page() -> None:
    with layout(current_path="/my-page"):
        # Your content here
        ui.label("Hello")
```

**Navigation Items**:
```
🔍 Vyhľadávanie     /
🏢 Obstaravatelia   /procurers
🤝 Dodavatelia      /suppliers
ℹ️  O aplikácii      /about
```

### @ui.refreshable

Decorator from NiceGUI for conditional re-rendering.

```python
@ui.refreshable
def my_view() -> None:
    if _state.loading:
        ui.spinner()
        return
    ui.label(_state.query)

# Trigger re-render
my_view.refresh()
```

## Environment Variables

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `STORAGE_SECRET` | string | — | Yes | Secret key for NiceGUI session storage |
| `MONGO_PASSWORD` | string | — | Yes | Password for MongoDB |
| `NEO4J_PASSWORD` | string | — | Yes | Password for Neo4j |
| `EKOSYSTEM_BASE_URL` | string | `https://datahub.ekosystem.slovensko.digital` | No | Ekosystem Datahub URL |
| `EKOSYSTEM_API_TOKEN` | string | `` | No | Ekosystem API token (future use) |
| `TED_BASE_URL` | string | `https://api.ted.europa.eu` | No | TED API URL (future use) |
| `MCP_SERVER_URL` | string | `http://localhost:8000/mcp` | No | URL for GUI to reach MCP server |
| `GUI_HOST` | string | `0.0.0.0` | No | NiceGUI bind address |
| `GUI_PORT` | int | `8080` | No | NiceGUI port |
| `MCP_HOST` | string | `0.0.0.0` | No | MCP server bind address |
| `MCP_PORT` | int | `8000` | No | MCP server port |
| `CACHE_TTL_SEARCH` | int | `300` | No | Search result cache TTL (seconds) |
| `CACHE_TTL_ENTITY` | int | `3600` | No | Entity lookup cache TTL (seconds) |
| `CACHE_TTL_DETAIL` | int | `1800` | No | Detail view cache TTL (seconds) |
| `REQUEST_TIMEOUT` | float | `30.0` | No | HTTP request timeout (seconds) |
| `LOG_LEVEL` | string | `INFO` | No | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Project Structure

```
uvo-search/
├── src/
│   ├── uvo_mcp/                          # Backend (MCP server)
│   │   ├── __main__.py                   # Entry point: main()
│   │   ├── __init__.py
│   │   ├── server.py                     # FastMCP setup, lifespan context
│   │   ├── config.py                     # Settings (pydantic-settings)
│   │   ├── models.py                     # Pydantic response models
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── procurements.py           # search_completed_procurements, get_procurement_detail
│   │       └── subjects.py               # find_procurer, find_supplier
│   │
│   └── uvo_gui/                          # Frontend (NiceGUI)
│       ├── __main__.py                   # Entry point: main()
│       ├── main.py                       # (deprecated, use __main__)
│       ├── app.py                        # NiceGUI app setup: start()
│       ├── config.py                     # GuiSettings (pydantic-settings)
│       ├── mcp_client.py                 # HTTP MCP client: call_tool()
│       ├── pages/
│       │   ├── __init__.py
│       │   ├── search.py                 # Route: /, State: SearchState
│       │   ├── procurers.py              # Route: /procurers, State: ProcurersState
│       │   ├── suppliers.py              # Route: /suppliers, State: SuppliersState
│       │   └── about.py                  # Route: /about (no state)
│       └── components/
│           ├── __init__.py
│           └── layout.py                 # Shared layout shell: layout()
│
├── tests/
│   ├── conftest.py                       # pytest_plugins = ["nicegui.testing.general_fixtures"]
│   ├── mcp/
│   │   ├── test_procurements.py
│   │   └── test_subjects.py
│   └── gui/
│       ├── layout_test_app.py            # Minimal test app for layout testing
│       ├── test_search.py
│       ├── test_procurers.py
│       ├── test_suppliers.py
│       └── test_about.py
│
├── docs/
│   ├── architecture.md                   # System design and data flow
│   ├── frontend.md                       # Frontend (NiceGUI) guide
│   ├── backend.md                        # Backend (MCP) guide
│   ├── reference.md                      # This file
│   ├── plan.md                           # Project roadmap
│   ├── data-sources-research.md          # API documentation
│   ├── nicegui-research.md               # NiceGUI patterns
│   └── superpowers/
│
├── .github/workflows/
│   ├── ci.yml                            # Unit tests, lint, Docker build
│   └── docker-publish.yml                # Push to registry on tag
│
├── Dockerfile.mcp                        # MCP server image
├── Dockerfile.gui                        # GUI image
├── docker-compose.yml                    # Local deployment
├── pyproject.toml                        # Dependencies, tooling config
├── uv.lock                               # Locked dependency versions
├── .env.example                          # Configuration template
├── CLAUDE.md                             # Development context
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
# Edit .env and set STORAGE_SECRET, MONGO_PASSWORD, NEO4J_PASSWORD
```

### Run Local

```bash
# Terminal 1: MCP server
uv run python -m uvo_mcp

# Terminal 2: GUI
uv run python -m uvo_gui

# Open http://localhost:8080
```

### Run with Hot Reload

```bash
# MCP server (auto-restarts on code change)
uv run watchfiles 'python -m uvo_mcp' src/uvo_mcp

# GUI (auto-reloads via NiceGUI)
uv run python -m uvo_gui
```

### Test

```bash
# All tests (gui and mcp)
uv run pytest tests/gui/ tests/mcp/ -v

# GUI tests only
uv run pytest tests/gui/ -v

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

### Call MCP Tool from Frontend

```python
from uvo_gui import mcp_client

# In async function
data = await mcp_client.call_tool(
    "search_completed_procurements",
    {"text_query": "software", "limit": 20, "offset": 0}
)
# data = {"data": [...], "total": N}
```

### Module-Level State + Refreshable

```python
from dataclasses import dataclass, field
from nicegui import ui

@dataclass
class MyState:
    query: str = ""
    results: list = field(default_factory=list)
    
    async def search(self) -> None:
        my_view.refresh()  # Show loading
        try:
            data = await mcp_client.call_tool(...)
            self.results = data.get("items", [])
        finally:
            my_view.refresh()  # Show results

_state = MyState()

@ui.refreshable
def my_view() -> None:
    for item in _state.results:
        ui.label(item.get("nazov"))

@ui.page("/my")
async def my_page() -> None:
    with layout(current_path="/my"):
        my_view()
```

### Async Button Click

```python
import asyncio

ui.button(
    "Next",
    on_click=lambda: asyncio.ensure_future(_state.goto_page(_state.page + 1))
)
```

## URLs & External Resources

| Resource | Link |
|----------|------|
| **UVO Vestník** | https://www.uvo.gov.sk/vestnik |
| **NKOD (data.gov.sk)** | https://data.gov.sk |
| **ITMS Open Data** | https://www.itms2014.sk/ |
| **NiceGUI** | https://nicegui.io |
| **FastMCP** | https://github.com/anthropics/mcp-py-server |
| **TED API** | https://ted.europa.eu/api |
| **Ekosystem Datahub** | https://datahub.ekosystem.slovensko.digital |

## Dependencies

**Runtime**:
- `mcp[cli]>=1.0.0` — Model Context Protocol (Anthropic)
- `nicegui>=3.9.0` — Web UI framework
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
