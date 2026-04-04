# UVO Search

Search and browse Slovak government procurement data via a dual-interface application — use an AI agent through MCP or browse through a web interface.

## Features

- **Full-text search** across government procurement records from [UVOstat.sk](https://www.uvostat.sk/)
- **Structured filtering** by CPV codes (EU product classification), date ranges, procurement authorities, and suppliers
- **MCP server** with 4 tools for AI agent integration — search procurements, find procurers and suppliers
- **NiceGUI web frontend** with server-side pagination, detail views, and entity browsing (fully in Slovak)
- **Dual access** — use the same backend with Claude Desktop/Code (via stdio) or in your browser (via HTTP)
- **Caching layer** with configurable TTLs to respect API rate limits
- **Docker Compose deployment** with health checks for both services

## Architecture

UVO Search runs as a **two-process Python application** communicating over HTTP:

```
┌─────────────────┐
│   Browser       │ ──HTTP──┐
│   (user)        │         │
└─────────────────┘         │
                            ├──→ NiceGUI Frontend (port 8080)
┌─────────────────┐         │    ├─ Search pages (Vyhľadávanie)
│  Claude Desktop │ ──stdio─┤    ├─ Procurement browsers
│  Claude Code    │         │    └─ Detail views
└─────────────────┘         │         │
                            │         │ (MCP client)
                            │         │
                            └──→ MCP Server (port 8000)
                                 ├─ 7 tools (search, detail, find, contracts)
                                 ├─ TTL caching
                                 └─ REST client for external APIs
                                      │
                                      ├─ UVOstat API
                                      ├─ Ekosystem Datahub
                                      ├─ TED API (EU procurements)
                                      └─ RPVS/OpenSanctions (beneficial ownership)
```

**Why two processes?**

1. **Independent scaling** — MCP server handles API calls and caching; GUI handles WebSocket connections
2. **Independent deployment** — update frontend without touching data layer
3. **Multiple clients** — Claude Desktop/Code connect via stdio; the GUI connects via HTTP
4. **Simpler debugging** — isolate data issues from UI issues

## Quick Start

### Prerequisites

- **Python 3.12+**
- **uv** package manager (install from https://docs.astral.sh/uv/getting-started/)
- **UVOstat API token** (request at https://www.uvostat.sk/api or use CSV bulk download as fallback)

### Local Development Setup

```bash
# Clone and enter project
git clone https://github.com/your-org/uvo-search.git
cd uvo-search

# Create .env with your API token
cp .env.example .env
# Edit .env and set UVOSTAT_API_TOKEN=your-actual-token

# Install dependencies
uv sync --all-extras

# Run both services (in separate terminals)
# Terminal 1: MCP server
uv run python -m uvo_mcp

# Terminal 2: GUI
uv run python -m uvo_gui

# Open browser to http://localhost:8080
```

### Running Tests

```bash
# Unit tests (mocked API responses)
uv run pytest tests/ -m "not e2e and not integration" -v

# With coverage
uv run pytest tests/ -m "not e2e and not integration" --cov=src/

# Lint check
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

## Running with Docker Compose

### Prerequisites

- Docker and Docker Compose

### Deployment

```bash
# Clone the project
git clone https://github.com/your-org/uvo-search.git
cd uvo-search

# Create .env file
cat > .env << 'EOF'
UVOSTAT_API_TOKEN=your-actual-token
STORAGE_SECRET=change-this-to-a-random-string
MCP_SERVER_URL=http://mcp-server:8000/mcp
EOF

# Build and start services
docker compose up -d --build

# Wait for services to be healthy (check logs)
docker compose logs -f

# Access the web interface
open http://localhost:8080

# Verify MCP server
curl http://localhost:8000/health
```

### Stopping Services

```bash
docker compose down -v
```

## MCP Server Tools

The MCP server provides 4 tools for AI agent integration:

| Tool | Description | Parameters |
|------|-------------|-----------|
| `search_completed_procurements` | Search awarded government contracts | `text_query`, `cpv_codes[]`, `procurer_id`, `supplier_ico`, `date_from`, `date_to`, `limit`, `offset` |
| `get_procurement_detail` | Get full details of a specific procurement | `procurement_id` |
| `find_procurer` | Find contracting authorities (obstaravatelia) | `name_query`, `ico`, `limit`, `offset` |
| `find_supplier` | Find suppliers who won contracts | `name_query`, `ico`, `limit`, `offset` |

### Current Implementation Status

The MVP includes 4 core tools. Future phases will add:
- `search_announced_procurements` — open bidding opportunities
- `get_subject_detail` — entity profiles with procurement history  
- `search_contracts` — CRZ contracts via Ekosystem Datahub

See [docs/plan.md](docs/plan.md) for the full implementation roadmap.

### Using with Claude

```bash
# Install as a local MCP server in Claude Desktop (macOS)
cd ~/.claude/servers
ln -s /path/to/uvo-search uvo-search

# Or add to ~/.claude/config.json
{
  "mcpServers": {
    "uvo-search": {
      "command": "python",
      "args": ["-m", "uvo_mcp", "stdio"]
    }
  }
}

# Claude will now have access to all 7 tools
```

## Configuration

All settings come from environment variables (via `.env` file):

| Variable | Required? | Default | Description |
|----------|-----------|---------|-------------|
| `UVOSTAT_API_TOKEN` | ✓ | — | API token for UVOstat.sk (get from https://www.uvostat.sk/api) |
| `STORAGE_SECRET` | ✓ | — | Secret key for NiceGUI session storage |
| `UVOSTAT_BASE_URL` | — | `https://www.uvostat.sk` | UVOstat API base URL |
| `EKOSYSTEM_BASE_URL` | — | `https://datahub.ekosystem.slovensko.digital` | Ekosystem Datahub base URL |
| `EKOSYSTEM_API_TOKEN` | — | `` | Optional token for Ekosystem (not required for public endpoints) |
| `MCP_SERVER_URL` | — | `http://localhost:8000/mcp` | URL where GUI reaches MCP server |
| `GUI_HOST` | — | `0.0.0.0` | NiceGUI bind host |
| `GUI_PORT` | — | `8080` | NiceGUI port |
| `MCP_HOST` | — | `0.0.0.0` | MCP server bind host |
| `MCP_PORT` | — | `8000` | MCP server port |
| `CACHE_TTL_SEARCH` | — | `300` | TTL in seconds for search results cache |
| `CACHE_TTL_ENTITY` | — | `3600` | TTL in seconds for entity lookups cache |
| `CACHE_TTL_DETAIL` | — | `1800` | TTL in seconds for detail views cache |
| `REQUEST_TIMEOUT` | — | `30.0` | HTTP request timeout in seconds |
| `LOG_LEVEL` | — | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## GUI Structure

The web frontend is built with **NiceGUI** (FastAPI + Vue/Quasar + Tailwind CSS) with a fully Slovak interface:

- **Vyhľadávanie (Search)** — Main page with full-text and structured filtering for procurements
- **Obstaravatelia (Procurers)** — Browse contracting authorities and their procurement history
- **Dodavatelia (Suppliers)** — Browse companies that won government contracts
- **Detail views** — Complete procurement records with associated contracts and suppliers

All pages support **server-side pagination** and are optimized for both desktop and mobile browsers.

## Development

### Project Structure

```
uvo-search/
├── src/
│   ├── uvo_mcp/                 # MCP server (Python)
│   │   ├── __main__.py          # Entry point
│   │   ├── server.py            # FastMCP setup with httpx lifespan
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── models.py            # Pydantic response models
│   │   └── tools/
│   │       ├── procurements.py  # Search/detail tools
│   │       └── subjects.py      # Entity lookup tools
│   │
│   └── uvo_gui/                 # NiceGUI frontend (Python)
│       ├── __main__.py          # Entry point
│       ├── app.py               # NiceGUI app setup
│       ├── config.py            # GUI settings
│       ├── mcp_client.py        # HTTP MCP client
│       ├── pages/
│       │   └── search.py        # Main search page
│       └── components/
│           ├── nav_header.py    # Navigation bar
│           └── detail_dialog.py # Detail view modal
│
├── tests/
│   ├── mcp/                     # Unit tests for MCP server
│   ├── gui/                     # Unit tests for GUI
│   └── e2e/                     # End-to-end tests (require docker compose)
│
├── docs/
│   ├── plan.md                  # Project overview
│   ├── superpowers/specs/       # Full design specification
│   ├── data-sources-research.md # API documentation and research
│   └── nicegui-research.md      # NiceGUI patterns and capabilities
│
├── .github/workflows/
│   ├── ci.yml                   # Unit tests, lint, Docker build
│   └── docker-publish.yml       # Push to container registry
│
├── Dockerfile.mcp               # MCP server container
├── Dockerfile.gui               # GUI container
├── docker-compose.yml           # Local deployment
├── pyproject.toml               # Dependencies and tooling
├── uv.lock                      # Locked dependency versions
└── .env.example                 # Configuration template
```

### Running Locally with Hot Reload

**MCP Server** (auto-reloads on code changes):
```bash
uv run watchfiles 'python -m uvo_mcp' src/uvo_mcp
```

**GUI** (auto-reloads via NiceGUI):
```bash
uv run python -m uvo_gui
```

### Code Style

Code is checked with **ruff** (linter and formatter):

```bash
# Check for issues
uv run ruff check src/ tests/

# Auto-fix issues
uv run ruff check --fix src/ tests/

# Format code
uv run ruff format src/ tests/
```

Configuration in `pyproject.toml`:
- Line length: 100
- Target Python: 3.12+
- Enabled rules: E, F, I, UP (imports, basic, upgrade)

## CI/CD

### GitHub Actions Workflows

**ci.yml** — Runs on every push and PR:
1. **Unit Tests** — pytest with mocked API responses
2. **Lint** — ruff check and format validation
3. **Docker Build** — build both images (MCP and GUI)
4. **Docker Compose** — start full stack and run E2E tests

**docker-publish.yml** — Publishes images on tag:
- Builds and pushes `your-registry/uvo-search-mcp:latest`
- Builds and pushes `your-registry/uvo-search-gui:latest`

## Data Sources

The application integrates with multiple Slovak and EU data sources:

| Source | Type | Access | Used For |
|--------|------|--------|----------|
| [UVOstat.sk](https://www.uvostat.sk) | Procurement API | REST (token required) | Primary source: completed & announced procurements |
| [Ekosystem Datahub](https://datahub.ekosystem.slovensko.digital) | Government data | REST API (free, rate-limited) | CRZ contracts, legal entities, accounting data |
| [TED API](https://ted.europa.eu/api/) | EU procurement | REST (anonymous) | EU-wide procurements (cross-reference) |
| [RPVS/OpenSanctions](https://www.opensanctions.org/datasets/sk_rpvs/) | Beneficial ownership | Download/API | Corporate beneficial owners |
| [CRZ](https://crz.gov.sk) | Government contracts | Via Ekosystem | All government contracts above threshold |

### Data Freshness

- **UVOstat** — Updated daily, delay ~24 hours from publication
- **CRZ** — Updated daily via Ekosystem Datahub
- **TED** — Updated daily, international standardization lag
- **Beneficial ownership** — Updated quarterly via RPVS

## Error Handling

The application implements **graceful degradation**:

- If a data source is unavailable, the app continues with reduced functionality
- API timeouts default to 30 seconds (configurable)
- Rate limits are handled via TTL caching
- HTTP 429 (Too Many Requests) returns cached results if available

## License

MIT (or see LICENSE file in repository)

## Documentation

For more details, see:
- **[Design Specification](docs/superpowers/specs/2026-04-03-uvo-search-design.md)** — Full architecture, data models, deployment
- **[Data Sources Research](docs/data-sources-research.md)** — API endpoints, data structure, open source projects
- **[NiceGUI Research](docs/nicegui-research.md)** — UI patterns, pagination, component structure
- **[Project Plan](docs/plan.md)** — Phased implementation roadmap, risks, and mitigations

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for development guidelines, testing requirements, and code review process.

---

**Questions or Issues?** Open a GitHub issue or discussion. For API-related questions, check the [UVOstat API documentation](https://github.com/MiroBabic/uvostat_api).
