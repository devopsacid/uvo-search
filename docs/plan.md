# UVO SEARCH

## App Definition

Application for searching and browsing Slovak government procurement data from https://www.uvo.gov.sk/

### Primary Data Source
- **UVOstat.sk API** (https://www.uvostat.sk/api) — structured procurement data (2014+)
- API docs: https://github.com/MiroBabic/uvostat_api
- Requires ApiToken header; CSV bulk download available at https://www.uvostat.sk/download

### Secondary Data Sources
- **Ekosystem.Slovensko.Digital Datahub** — CRZ contracts, legal entities (free REST API, 60 req/min)
- **TED API** (EU procurement, anonymous access) — cross-reference for above-threshold procurements
- **RPVS / OpenSanctions** — beneficial ownership data

### Architecture
Two-process Python application:
1. **MCP Server** (port 8000) — FastMCP wrapping UVOstat API + secondary sources, dual transport (stdio for Claude, streamable-http for GUI)
2. **NiceGUI Frontend** (port 8080) — web search interface with server-side paginated tables, detail views, entity browsing

### Tech Stack
- Python 3.12+, uv, async throughout
- MCP SDK (FastMCP), httpx, Pydantic, cachetools
- NiceGUI v3.9+ (FastAPI + Vue/Quasar + Tailwind)
- Docker Compose for deployment

## Documentation

| Document | Description |
|----------|-------------|
| [Design Spec](superpowers/specs/2026-04-03-uvo-search-design.md) | Full architecture, MCP tools, GUI pages, data models, deployment, testing |
| [MCP + GUI Research](research.md) | MCP server patterns, NiceGUI vs alternatives, integration architecture |
| [NiceGUI Research](nicegui-research.md) | NiceGUI capabilities, code patterns, FastAPI integration, deployment |
| [Data Sources Research](data-sources-research.md) | UVOstat API endpoints, UVO.gov.sk structure, open source projects, alternative data sources, data model |

## Implementation Phases

### Phase 1: MVP (3-4 days)
- MCP server with 4 core tools (search_completed_procurements, get_procurement_detail, find_procurer, find_supplier)
- Basic NiceGUI search page with server-side pagination
- Unit tests with mocked HTTP responses

### Phase 2: Core Features (3-4 days)
- All 7 MCP tools including Ekosystem Datahub contracts
- Multi-page GUI (procurers, suppliers, detail with tabs)
- Caching layer, reusable search filter components

### Phase 3: Enrichment (3-5 days)
- TED API + RPVS/OpenSanctions integration
- CSV export, CPV code browser
- Beneficial ownership display

### Phase 4: Production (2-3 days)
- Docker Compose deployment
- Health checks, logging, responsive design
- Rate limit handling, error UX

## Key Risks
1. **UVOstat API token** — acquisition process unclear; fallback: CSV bulk download → local SQLite
2. **Rate limits** — mitigated by TTL caching (5 min search, 1 hour entities)
3. **Data freshness** — daily updates acceptable for target users (researchers, journalists, businesses)

## Research Findings Summary

### Open Source Projects (relevant)
- [CRZ-scraper](https://github.com/slovak-egov/CRZ-scraper) — Python scraper for crz.gov.sk
- [verejne.digital](https://github.com/verejnedigital/verejne.digital) — AI analysis of Slovak public data
- [OpenSanctions RPVS](https://www.opensanctions.org/datasets/sk_rpvs/) — beneficial ownership data
- [byrokrat-sk/register-parser](https://github.com/byrokrat-sk/register-parser) — PHP ORSR parser
- [UVOstat API docs](https://github.com/MiroBabic/uvostat_api) — API documentation

### Data Sources for Government/Company/Contract Information
| Source | Type | Access |
|--------|------|--------|
| UVOstat.sk | Procurement data | API (token required) |
| Ekosystem.Slovensko.Digital | CRZ contracts, legal entities, accounting | REST API (free) |
| TED (EU) | EU-wide procurement | REST API (anonymous) |
| RPVS | Beneficial ownership | API via Ministry of Justice |
| CRZ (crz.gov.sk) | All government contracts | Via Datahub API or XML |
| ORSR (orsr.sk) | Business register | HTML scraping only |
| FinStat.sk | Company financials | Commercial API |
| data.gov.sk | Open datasets | CKAN portal |
| UVO.gov.sk Vestnik | Official procurement bulletin | Monthly XML downloads |
| otvorenezmluvy.sk | Contract analytics | Web (Transparency Int'l SK) |
