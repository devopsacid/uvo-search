# UVO Search

Search and browse Slovak government procurement data via a dual-interface application — use an AI agent through MCP or browse through a web interface.

## Features

- **Full-text search** across Slovak government procurement records (UVO Vestník, CRZ, ITMS, TED, NKOD)
- **Structured filtering** by CPV codes (EU product classification), date ranges, procurement authorities, and suppliers
- **Ingestion dashboard** — Monitor pipeline health, data freshness, cross-source deduplication, and per-source ingestion trends
- **MCP server** with 4 tools for AI agent integration — search procurements, find procurers and suppliers
- **React SPA frontend** (Vite 5 + React 18 + TypeScript) — Public web UI with client-side routing, advanced filtering, and graphs
- **Dual access** — use the same backend with Claude Desktop/Code (via stdio) or in your browser (via HTTP)
- **Caching layer** with configurable TTLs to respect API rate limits
- **Docker Compose deployment** with health checks for all services
- **Vitest + Testing Library** for React frontend; Playwright e2e tests

## Architecture

UVO Search is a **three-process application** with shared MCP backend:

```
┌──────────────────────────────────────────────┐
│ MCP Server (Python, port 8000)               │
│ ├─ 4 tools (search, detail, find, contracts)│
│ ├─ Graph tools (ego, cpv networks)          │
│ ├─ TTL caching via cachetools               │
│ └─ REST clients for external APIs           │
└──────────────────────────────────────────────┘
            ↑                          ↑
    ┌───────┴──────┐            ┌──────┴────┐
    │              │            │  (stdio)  │
    │ (HTTP)       │            │           │
    │              │            │           │
┌───┴────────────┐         ┌────┴───────┐
│ React SPA      │         │  Claude    │
│ (port 8080)    │         │  Desktop/  │
│ Vite+React+TS  │         │  Code      │
├────────────────┤         └────────────┘
│ • Search       │
│ • Procurers    │
│ • Suppliers    │
│ • Graphs       │
│ • CPV trends   │
└────────────────┘

External sources:
├─ UVO Vestník (Slovak procurement notices, XML)
├─ Ekosystem Datahub / CRZ (Slovak contracts)
├─ ITMS (EU structural funds)
├─ TED API (EU procurements)
└─ NKOD (national open data catalog)
```

**Why split MCP server and GUI?**

1. **Independent scaling** — MCP server handles API calls and caching; GUI handles WebSocket connections
2. **Independent deployment** — update frontend without touching data layer
3. **Multiple clients** — Claude Desktop/Code connect via stdio; the GUI connects via HTTP
4. **Simpler debugging** — isolate data issues from UI issues

### Search stack

Search uses **MongoDB Atlas Local** (`mongodb/mongodb-atlas-local` image) which ships
with `mongot`, Atlas Search's engine. A `sk_folding` custom analyzer (standard
tokenizer + `lowercase` + `icuFolding`) is applied to text fields on procurers,
suppliers, and notices, so queries are case- and diacritic-insensitive. Name
fields also carry an `autocomplete` (edgeGram) subfield powering the live search
dropdown.

Supported query patterns in the GUI search box:

- plain words — fuzzy match via autocomplete + full-text scoring
- `"exact phrase"` — phrase match
- `fak*`, `fak?lta` — wildcard match
- empty — list all, paginated and sortable

### Relationship graph

The `/graph` page renders procurer–supplier networks pulled from Neo4j via
`graph_ego_network` (pick an entity, choose hop depth) and `graph_cpv_network`
(pick a CPV code + year) MCP tools. Rendering uses `vis-network` loaded from CDN.

### Migrating legacy data

After the image swap, run `scripts/migrate_to_atlas_local.sh` once to copy
existing data. The MCP server creates Atlas Search indexes on startup.

## Quick Start

### Prerequisites

- **Python 3.12+**
- **uv** package manager (install from https://docs.astral.sh/uv/getting-started/)

### Local Development Setup

```bash
# Clone and enter project
git clone https://github.com/your-org/uvo-search.git
cd uvo-search

# Create .env from template
cp .env.example .env
# Edit .env and set MONGO_PASSWORD, NEO4J_PASSWORD

# Install Python dependencies
uv sync --all-extras

# Run MCP server (Terminal 1)
uv run python -m uvo_mcp

# Run API bridge (Terminal 2)
uv run python -m uvo_api

# Run React public frontend (Terminal 3)
cd src/uvo-gui-react
npm install
npm run dev
# Open browser to http://localhost:5174
```

### Running Tests

```bash
# Backend unit tests (MCP server, API, mocked responses)
uv run pytest tests/mcp/ tests/api/ -v

# React frontend unit tests (Vitest + Testing Library)
cd src/uvo-gui-react
npm test

# E2E browser tests (requires docker compose running)
cd ../.. && uv run pytest tests/e2e/ -v

# With coverage
uv run pytest tests/mcp/ tests/api/ --cov=src/ -v

# Lint check
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# React linting
cd src/uvo-gui-react && npm run lint
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
MCP_SERVER_URL=http://mcp-server:8000/mcp
EOF

# Build and start services
docker compose up -d --build

# Wait for services to be healthy (check logs)
docker compose logs -f

# Access the web interface
open http://localhost:8080

# Or access via Docker service name inside stack
curl http://gui-react:5173/

# Verify MCP server
curl http://localhost:8000/health
```

### Stopping Services

```bash
docker compose down -v
```

## MCP Server Tools

The MCP server provides 6 tools for AI agent integration:

| Tool | Description | Parameters |
|------|-------------|-----------|
| `search_completed_procurements` | Search awarded government contracts | `text_query`, `cpv_codes[]`, `procurer_id`, `supplier_ico`, `date_from`, `date_to`, `limit`, `offset` |
| `get_procurement_detail` | Get full details of a specific procurement | `procurement_id` |
| `find_procurer` | Find contracting authorities (obstaravatelia) | `name_query`, `ico`, `limit`, `offset` |
| `find_supplier` | Find suppliers who won contracts | `name_query`, `ico`, `limit`, `offset` |
| `graph_ego_network` | Entity relationship network (procurer/supplier ego graph) | `ico`, `entity_type`, `hops` |
| `graph_cpv_network` | CPV code procurement network (by year) | `cpv_code`, `year`, `limit` |

### API Dashboard Endpoints

- `GET /api/dashboard/ingestion` — Pipeline health snapshot (source status, per-source daily ingestion, dedup metrics, latest run metadata)

### Current Implementation Status

Core tools (4) + graph tools (2). Future phases will add:
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
| `EKOSYSTEM_BASE_URL` | — | `https://datahub.ekosystem.slovensko.digital` | Ekosystem Datahub base URL |
| `EKOSYSTEM_API_TOKEN` | — | `` | Optional token for Ekosystem (not required for public endpoints) |
| `MCP_SERVER_URL` | — | `http://localhost:8000/mcp` | URL where GUI reaches MCP server |
| `MCP_HOST` | — | `0.0.0.0` | MCP server bind host |
| `MCP_PORT` | — | `8000` | MCP server port |
| `CACHE_TTL_SEARCH` | — | `300` | TTL in seconds for search results cache |
| `CACHE_TTL_ENTITY` | — | `3600` | TTL in seconds for entity lookups cache |
| `CACHE_TTL_DETAIL` | — | `1800` | TTL in seconds for detail views cache |
| `REQUEST_TIMEOUT` | — | `30.0` | HTTP request timeout in seconds |
| `LOG_LEVEL` | — | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Frontend

Built with **Vite 5 + React 18 + TypeScript**, modern single-page application:

- **Overview** — Dashboard with annual trends and CPV breakdown
- **Search** — Full-text and structured filtering (dates, CPV codes, entities)
- **Suppliers** — Browse awarded contractors by name, ICO, or contract count
- **Procurers** — Browse contracting authorities and procurement spending
- **Ingestion** — Monitor pipeline health, data freshness per source, deduplication metrics, and 30-day ingestion trends
- **Graphs** — Interactive network visualization (Cytoscape.js)
  - Ego network: procurer/supplier relationships (configurable hop depth)
  - CPV network: procurement patterns by product category
- **CPV Trends** — Historical spend analysis by procurement code
- **Calendar** — Timeline view of procurements
- **Concentration Analysis** — HHI supplier concentration metrics

**Features:**
- **URL-as-state:** All filters, pagination, sort live in query params (bookmarkable)
- **TanStack Query:** Efficient data fetching with caching
- **Tailwind CSS + shadcn/ui:** Modern, accessible component library
- **Lazy-loaded graph chunk:** Code splitting for large Cytoscape bundle
- **Mobile-optimized:** Responsive sidebar and touch-friendly interactions

---

## Development

### Project Structure

```
uvo-search/
├── src/
│   ├── uvo_mcp/                      # MCP server (Python)
│   │   ├── __main__.py               # Entry point
│   │   ├── server.py                 # FastMCP setup with httpx lifespan
│   │   ├── config.py                 # Settings (pydantic-settings)
│   │   ├── models.py                 # Pydantic response models
│   │   └── tools/
│   │       ├── procurements.py       # Search/detail tools
│   │       ├── subjects.py           # Entity lookup tools
│   │       └── graph.py              # Graph tools (ego, cpv networks)
│   │
│   ├── uvo_api/                      # FastAPI bridge (Python)
│   │   ├── __main__.py               # Entry point
│   │   ├── main.py                   # App setup
│   │   ├── config.py                 # Settings
│   │   ├── mcp_client.py             # HTTP MCP client
│   │   └── routers/
│   │       ├── contracts.py          # Contract endpoints
│   │       ├── dashboard.py          # Dashboard endpoints
│   │       ├── procurers.py          # Procurer endpoints
│   │       ├── suppliers.py          # Supplier endpoints
│   │       └── graph.py              # Graph endpoints
│   │
│   └── uvo-gui-react/                # React SPA public frontend
│       ├── src/
│       │   ├── pages/                # Route components (Search, Suppliers, etc.)
│       │   ├── components/           # Reusable UI components
│       │   ├── hooks/                # Custom React hooks
│       │   ├── lib/                  # Utilities (cn, api client)
│       │   ├── i18n/                 # Translations (Slovak)
│       │   ├── test/                 # Vitest unit tests
│       │   ├── router.tsx            # React Router 6 routes
│       │   └── App.tsx               # Root component
│       ├── vite.config.ts            # Vite bundler config
│       ├── tsconfig.json             # TypeScript config
│       ├── tailwind.config.js        # Tailwind CSS config
│       ├── vitest.config.ts          # Vitest test config
│       └── package.json              # npm dependencies
│
├── tests/
│   ├── mcp/                          # Unit tests for MCP server
│   ├── api/                          # Unit tests for API
│   └── e2e/                          # End-to-end tests (require docker compose)
│
├── docs/
│   ├── plan.md                       # Project overview
│   ├── architecture.md               # Architecture documentation
│   ├── backend.md                    # Backend (MCP) documentation
│   ├── superpowers/specs/            # Full design specifications
│   └── data-sources-research.md      # API documentation and research
│
├── .github/workflows/
│   ├── ci.yml                        # Unit tests, lint, Docker build
│   └── docker-publish.yml            # Push to container registry
│
├── docker-compose.yml                # Local deployment
├── Dockerfile.mcp                    # MCP server container
├── Dockerfile.api                    # API container
├── src/uvo-gui-react/Dockerfile      # React app container
├── pyproject.toml                    # Python dependencies and tooling
├── uv.lock                           # Locked Python dependency versions
└── .env.example                      # Configuration template
```

### Running Locally with Hot Reload

**MCP Server** (auto-reloads on code changes):
```bash
uv run watchfiles 'python -m uvo_mcp' src/uvo_mcp
```

**React GUI** (Vite dev server with HMR):
```bash
cd src/uvo-gui-react && npm run dev
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
3. **Docker Build** — build the MCP image
4. **Docker Compose** — start full stack and run E2E tests

**docker-publish.yml** — Publishes images on tag:
- Builds and pushes `your-registry/uvo-search-mcp:latest`

## Data Sources

The application integrates with multiple Slovak and EU data sources:

| Source | Type | Access | Used For |
|--------|------|--------|----------|
| [UVO Vestník](https://www.uvo.gov.sk/vestnik) | Procurement notices (XML) | Anonymous download | Primary source: announced & completed procurements |
| [Ekosystem Datahub / CRZ](https://datahub.ekosystem.slovensko.digital) | Government data | REST API (free, rate-limited) | CRZ contracts, legal entities, accounting data |
| [ITMS](https://www.itms2014.sk/) | EU structural funds | Open data / REST | ITMS-funded projects and contracts |
| [TED API](https://ted.europa.eu/api/) | EU procurement | REST (anonymous) | EU-wide procurements (cross-reference) |
| [NKOD](https://data.gov.sk) | National Open Data Catalog | CKAN / DCAT | Catalog metadata and dataset discovery |

### Data Freshness

- **UVO Vestník** — Published on the official UVO schedule (several times per week)
- **CRZ** — Updated daily via Ekosystem Datahub
- **ITMS** — Updated on the ITMS open-data publication cadence
- **TED** — Updated daily, international standardization lag
- **NKOD** — Catalog refreshed by the publisher

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
- **[Project Plan](docs/plan.md)** — Phased implementation roadmap, risks, and mitigations

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for development guidelines, testing requirements, and code review process.

---

**Questions or Issues?** Open a GitHub issue or discussion.
