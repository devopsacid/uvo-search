# UVO Search -- MCP Server + GUI Research

**Date:** 2026-04-03
**Status:** Research complete, ready for architecture decisions

---

## Research Summary

This document covers five research areas for building an MCP server that wraps the UVOstat.sk procurement API and connects it to a web GUI:

1. MCP Server architecture in Python
2. Best practices for MCP tool design
3. MCP + GUI integration patterns
4. Python GUI framework comparison
5. Similar government data MCP servers and Slovak open data sources

---

## 1. MCP Server Architecture in Python

### Core Library: `mcp` Python SDK (FastMCP)

**Installation:**
```bash
uv add "mcp[cli]"
# or
pip install "mcp[cli]"
```

**Requires:** Python 3.10+

The official SDK provides **FastMCP**, a high-level API that uses decorators to define tools, resources, and prompts. It handles protocol negotiation, schema generation, validation, and transport automatically.

### Recommended Project Structure

```
uvo-search/
├── pyproject.toml
├── README.md
├── src/
│   └── uvo_mcp/
│       ├── __init__.py
│       ├── __main__.py          # Entry point: python -m uvo_mcp
│       ├── server.py            # FastMCP server definition + tool registration
│       ├── config.py            # Settings (API token, base URL, timeouts)
│       ├── client.py            # httpx async client for UVOstat API
│       ├── models.py            # Pydantic models for API responses
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── procurements.py  # Tools for ukoncene/vyhlasene obstaravania
│       │   ├── subjects.py      # Tools for obstaravatelia/dodavatelia
│       │   └── contracts.py     # Tools for CRZ contracts
│       └── utils/
│           ├── __init__.py
│           ├── pagination.py    # Pagination helper (offset-based)
│           └── cache.py         # Simple TTL cache
├── gui/
│   └── app.py                   # Web GUI application
├── tests/
│   ├── test_tools.py
│   ├── test_client.py
│   └── conftest.py
└── docs/
    ├── plan.md
    └── research.md
```

### Core Server Pattern

```python
# src/uvo_mcp/server.py
from mcp.server.fastmcp import FastMCP
import httpx

mcp = FastMCP(
    "UVO Search",
    description="Search Slovak government procurement data from uvostat.sk",
    json_response=True,
)

# Shared async HTTP client via lifespan
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

@dataclass
class AppContext:
    http_client: httpx.AsyncClient

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    async with httpx.AsyncClient(
        base_url="https://www.uvostat.sk",
        headers={"ApiToken": settings.api_token},
        timeout=30.0,
    ) as client:
        yield AppContext(http_client=client)

mcp = FastMCP("UVO Search", lifespan=app_lifespan)
```

### Tool Definition Pattern (wrapping REST endpoints)

```python
from mcp.server.fastmcp import Context
from pydantic import Field

@mcp.tool()
async def search_completed_procurements(
    ctx: Context,
    cpv_codes: list[str] | None = Field(
        default=None,
        description="CPV classification codes to filter by, e.g. ['34121100-2']"
    ),
    procurer_id: str | None = Field(
        default=None,
        description="ID of the procuring entity"
    ),
    date_from: str | None = Field(
        default=None,
        description="Start date for publication filter (YYYY-MM-DD)"
    ),
    date_to: str | None = Field(
        default=None,
        description="End date for publication filter (YYYY-MM-DD)"
    ),
    limit: int = Field(default=20, ge=1, le=100, description="Max results (1-100)"),
    offset: int = Field(default=0, ge=0, description="Pagination offset"),
) -> dict:
    """Search completed government procurements from the Slovak UVO registry.

    Returns procurement records including contract details, procurer info,
    CPV codes, descriptions, and associated contracts.
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context
    params = {"limit": limit, "offset": offset}
    if cpv_codes:
        params["cpv[]"] = cpv_codes
    if procurer_id:
        params["obstaravatel_id[]"] = procurer_id
    if date_from:
        params["datum_zverejnenia_od"] = date_from
    if date_to:
        params["datum_zverejnenia_do"] = date_to

    try:
        response = await app_ctx.http_client.get(
            "/api/ukoncene_obstaravania", params=params
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        await ctx.error(f"API returned {e.response.status_code}")
        return {"error": str(e), "status_code": e.response.status_code}
    except httpx.RequestError as e:
        await ctx.error(f"Network error: {e}")
        return {"error": f"Request failed: {e}"}
```

### Transport Options

| Transport | Use Case | Configuration |
|-----------|----------|---------------|
| **stdio** | Claude Desktop, Claude Code, local MCP clients | `mcp.run(transport="stdio")` |
| **Streamable HTTP** | Web apps, remote clients, browser access | `mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)` |
| **SSE** | Legacy/older clients | `mcp.run(transport="sse")` |

For the GUI integration use case, **Streamable HTTP** is the correct choice -- it allows the MCP server to run as a standalone HTTP service that the web GUI can communicate with.

### Entry Point

```python
# src/uvo_mcp/__main__.py
from uvo_mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

---

## 2. Best Practices for MCP Servers

### Tool Design Principles

**Do NOT map REST endpoints 1:1 to MCP tools.** Instead, design tools around user intent:

| REST Endpoint | BAD MCP Tool | GOOD MCP Tool |
|---------------|-------------|---------------|
| `GET /api/ukoncene_obstaravania` | `get_ukoncene_obstaravania()` | `search_completed_procurements()` |
| `GET /api/vyhlasene_obstaravania` | `get_vyhlasene_obstaravania()` | `search_announced_procurements()` |
| `GET /api/subjekty?type=obstaravatel` | `get_subjekty()` | `find_procurer()` |

### Naming Conventions

- Use English, descriptive verb-noun names: `search_`, `find_`, `get_`, `list_`
- Keep names under 64 characters
- Group related tools with consistent prefixes: `procurement_search`, `procurement_details`

### Parameter Design

- Use descriptive parameter names with `Field(description=...)` -- the LLM reads these
- Provide sensible defaults (limit=20 not 100)
- Constrain ranges with `ge=`, `le=` validators
- Use `str | None` with defaults rather than required params where possible
- Translate domain jargon: `obstaravatel_id` -> `procurer_id` with clear description

### Docstrings Are Critical

The tool docstring is the primary way an LLM decides whether and how to call the tool. Write it as if explaining to a knowledgeable human:

```python
"""Search completed government procurements from the Slovak UVO registry.

Use this to find finalized procurement contracts. Filter by CPV codes
(EU standard product classification), date range, or procuring entity.
Returns contract details, winning suppliers, and contract values.

Examples:
- Find IT procurements since 2024: cpv_codes=["72000000-5"], date_from="2024-01-01"
- Find procurements by a specific entity: procurer_id="86958"
"""
```

### Error Handling

- Never let raw exceptions propagate -- always return structured error info
- Use `ctx.error()` for logging, but still return a dict with error details
- Distinguish between client errors (bad params), API errors (upstream), and network errors
- Include the HTTP status code when available

### Pagination

The UVOstat API uses offset-based pagination (limit/offset, max 100). Recommended patterns:

1. **Expose limit/offset directly** on tools (simplest, most flexible)
2. **Return pagination metadata** from the API's `summary` field so the caller knows total_records
3. **Provide a convenience tool** like `get_all_procurements()` that auto-paginates (use with caution -- can be slow)

### Caching

- Use `cachetools.TTLCache` or `aiocache` for response caching
- Cache read-only endpoints (procurement searches) with 5-15 minute TTL
- Cache entity lookups (procurer/supplier details) with longer TTL (1 hour)
- Do NOT cache search results with time-sensitive date filters at long TTLs

### Structured Output

Use Pydantic models for return types to get automatic schema validation:

```python
from pydantic import BaseModel

class ProcurementSummary(BaseModel):
    total_records: int
    offset: int
    limit: int

class ProcurementResult(BaseModel):
    summary: ProcurementSummary
    data: list[dict]

@mcp.tool()
async def search_completed_procurements(...) -> ProcurementResult:
    ...
```

---

## 3. MCP + GUI Integration

### Architecture Options

#### Option A: MCP Server as Backend, Separate Frontend (RECOMMENDED)

```
┌─────────────┐     HTTP/SSE      ┌─────────────┐    REST     ┌─────────────┐
│  Web GUI     │ ◄──────────────► │  MCP Server  │ ──────────► │ UVOstat API │
│  (Reflex /   │                  │  (FastMCP +  │             │             │
│   Streamlit) │                  │  Streamable  │             │             │
│              │                  │  HTTP)       │             │             │
└─────────────┘                   └─────────────┘             └─────────────┘
```

The MCP server runs with `streamable-http` transport. The GUI connects as an MCP client using the `mcp` Python SDK's client module. This gives you:
- Clean separation of concerns
- The MCP server is reusable (Claude Desktop, Claude Code, other agents can also connect)
- The GUI is just another MCP client

**GUI as MCP Client pattern:**
```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def call_mcp_tool(tool_name: str, arguments: dict):
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result
```

#### Option B: Direct API + MCP (Dual Interface)

```
┌─────────────┐     direct HTTP    ┌─────────────┐
│  Web GUI     │ ──────────────────► UVOstat API  │
│  (FastAPI +  │                   └─────────────┘
│   frontend)  │
└──────┬───────┘
       │ also exposes
       ▼
┌─────────────┐
│  MCP Server  │  (for AI agents)
└─────────────┘
```

The GUI calls the UVOstat API directly (simpler, faster), while the MCP server exists separately for AI agent use. This avoids the overhead of the MCP protocol for GUI-to-API communication but means duplicate API client code.

#### Option C: Claude Desktop / MCP Client

Use Claude Desktop or Claude Code with the MCP server connected via stdio transport. No custom GUI needed -- the AI provides the interface. Good for power users but not suitable as a standalone product.

### Recommendation

**Start with Option A.** It gives you a single source of truth (the MCP server) for all API interactions, and the GUI is a thin presentation layer. If latency becomes an issue, refactor to Option B.

### MCP-UI (Emerging Standard)

MCP-UI (https://mcpui.dev/) is an emerging open standard that lets MCP servers deliver interactive UI components directly inside chat/agent experiences. Still early-stage but worth watching for future integration with Claude Desktop.

---

## 4. Python GUI Framework Comparison

### For a procurement search/list interface, here is the comparison:

| Criteria | Streamlit | Reflex | FastAPI + React | Gradio | Panel |
|----------|-----------|--------|-----------------|--------|-------|
| **Dev Speed** | Fastest | Fast | Medium-Slow | Fast | Medium |
| **Search/Filter** | Good (st.text_input + manual) | Excellent (components) | Excellent (full control) | Basic | Good |
| **Table Display** | Good (st.dataframe) | Excellent (ag_grid, custom) | Excellent (any JS lib) | Basic | Good (Tabulator) |
| **Responsive** | Limited | Yes (React under hood) | Full control | Limited | Medium |
| **Pagination** | Manual | Built-in components | Full control | No | Manual |
| **State Mgmt** | Weak (reruns on interaction) | Strong (class-based) | Full control | Weak | Medium |
| **Production Ready** | Prototype/Internal | Yes | Yes | Prototype | Internal |
| **Python Only** | Yes | Yes | No (JS/TS needed) | Yes | Yes |
| **Learning Curve** | Very Low | Low-Medium | High | Very Low | Medium |

### Detailed Assessment

#### Streamlit
- **Pros:** Fastest to prototype. `st.dataframe()` handles tables well. Built-in caching (`@st.cache_data`). Large community. Free deployment on Streamlit Cloud.
- **Cons:** Entire script reruns on every interaction (bad for complex state). Limited custom styling. Not suitable for complex multi-page apps with persistent sessions. Pagination must be hand-rolled. No real component model.
- **Best for:** Quick internal tool, MVP, data exploration dashboard.

#### Reflex (RECOMMENDED for this project)
- **Pros:** Pure Python, compiles to FastAPI + React under the hood. Real component model with state management. Built-in auth, database ORM, responsive design. AG Grid integration for tables. No JavaScript required. Deployable as standard web app (containerizable).
- **Cons:** Smaller community than Streamlit. Documentation is improving but not as mature. Slightly more boilerplate than Streamlit for simple cases.
- **Best for:** Production web application with search, filtering, tables, and potential for growth into a full product.
- **Version:** 0.7.x (2026), actively developed, backed by YC.

#### FastAPI + React/Vue
- **Pros:** Maximum flexibility. Best performance. Full control over every pixel. Huge ecosystem of JS table/search components.
- **Cons:** Requires JavaScript/TypeScript expertise. Separate frontend build. More code to maintain. Slower iteration.
- **Best for:** When you need pixel-perfect UI or have a frontend developer on the team.

#### Gradio
- **Pros:** Very fast for ML demo interfaces. Good for chat-like interfaces.
- **Cons:** Not designed for data browsing/search applications. Limited table interaction. Weak filtering UI.
- **Best for:** ML model demos, not data search apps. Not recommended here.

#### Panel/Bokeh
- **Pros:** Strong data visualization. Good table widgets (Tabulator). Integrates with pandas.
- **Cons:** Steeper learning curve. Smaller community. Less modern feel.
- **Best for:** Data science dashboards with heavy visualization needs.

### Recommendation

**Primary: Reflex** -- It provides the right balance of Python-only development with production-quality output. The AG Grid integration handles complex table display, filtering, and sorting out of the box. State management is clean and scalable. The compiled React output means responsive design works well.

**Fallback: Streamlit** -- If development speed is the top priority and this is an internal tool / MVP, Streamlit gets you to a working prototype fastest.

---

## 5. Similar MCP Servers & Slovak Data Sources

### Government Data MCP Servers (Reference Implementations)

| Project | Language | APIs | Relevance |
|---------|----------|------|-----------|
| [datagouv-mcp](https://github.com/datagouv/datagouv-mcp) | Python | French Open Data (data.gouv.fr) | Closest match: government procurement data, search tools |
| [mcp-civic-data](https://github.com/EricGrill/mcp-civic-data) | Python | 13 US gov APIs | Good architecture reference: multi-API, tool grouping |
| [us-gov-open-data-mcp](https://github.com/lzinga/us-gov-open-data-mcp) | TypeScript | 40+ US gov APIs, 300+ tools | Massive scale reference, cross-referencing patterns |
| [datagov-mcp-server](https://github.com/melaodoidao/datagov-mcp-server) | Python | Data.gov | Simple reference implementation |
| [datagov-mcp](https://github.com/aviveldan/datagov-mcp) | Python | Israel Gov Data | Small-scale, clean implementation |

### Slovak Open Data Sources (Potential Additional Integrations)

| Source | URL | Data | Auth | Notes |
|--------|-----|------|------|-------|
| **UVOstat API** | https://www.uvostat.sk/api | Procurement data | ApiToken header | Primary target. Free tier for `/api/subjekty`, paid for other endpoints |
| **UVO.gov.sk** | https://www.uvo.gov.sk/ | Official procurement journal | Scraping needed | Raw source, no API |
| **RPVS API** | https://rpvs.gov.sk/opendatav2/swagger | Public sector partner registry | Free | REST API with Swagger docs, beneficial ownership data |
| **data.gov.sk** | https://data.gov.sk/ | National open data portal | Free | 9,900+ datasets, SPARQL endpoint |
| **ekosystem.slovensko.digital** | https://ekosystem.slovensko.digital/ | API catalog for Slovak gov | Varies | Aggregated API directory |
| **Slovak Statistics API** | https://slovak.statistics.sk/.../Open_data | Statistical data (DATAcube) | Free | Economic/demographic data |
| **otvorenezmluvy.sk** | https://otvorenezmluvy.sk/ | Contracts + analytics | Scraping | Run by Transparency International SK, red-flagging |
| **CRZ** (Central Register of Contracts) | https://crz.gov.sk/ | All government contracts | Scraping/RSS | Mandatory publication of all gov contracts |

### Key Insight: UVOstat API Access

The UVOstat API requires an **ApiToken** header for all requests. The `/api/subjekty` endpoint (entities/subjects) is **free** for registered users. Other endpoints (completed procurements, announced procurements) appear to require **paid access**. You will need to register at uvostat.sk to obtain a token and determine pricing for full API access.

---

## Integration Roadmap

### Phase 1: MCP Server MVP (1-2 days)

1. Set up Python project with `uv` and `pyproject.toml`
2. Install `mcp[cli]`, `httpx`, `pydantic`
3. Create basic MCP server with 3-4 tools:
   - `search_completed_procurements` (if API access allows)
   - `search_announced_procurements`
   - `find_procurer`
   - `find_supplier`
4. Test with Claude Code / Claude Desktop via stdio transport
5. Add Streamable HTTP transport for GUI use

### Phase 2: GUI Prototype (2-3 days)

1. Install Reflex (`pip install reflex`)
2. Build search page with:
   - Text input for keyword search
   - Date range picker
   - CPV code selector
   - Results table with AG Grid
3. Connect to MCP server as client
4. Add pagination controls

### Phase 3: Enrich & Harden (3-5 days)

1. Add caching layer (TTLCache for API responses)
2. Add RPVS integration (beneficial ownership lookups)
3. Add error handling, retry logic
4. Add export (CSV/JSON download)
5. Responsive design polish

### Phase 4: Production (ongoing)

1. Add authentication to the GUI
2. Deploy MCP server + GUI (Docker Compose)
3. Add monitoring/logging
4. Consider adding CRZ contract data
5. Consider adding data.gov.sk dataset search

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| UVOstat API requires paid access for key endpoints | High -- blocks core functionality | Register and check pricing early. Fallback: scrape UVO.gov.sk directly |
| UVOstat API rate limits unknown | Medium | Implement caching, add rate-limit handling (exponential backoff) |
| MCP Python SDK still evolving (v1.x stable, v2 pre-alpha) | Low | Pin to stable v1.x release, monitor changelog |
| Reflex is pre-1.0 (0.7.x) | Medium | Have Streamlit as fallback. Reflex is actively maintained and YC-backed |
| API token security | Medium | Use environment variables, never commit tokens. Add `.env` to `.gitignore` |

---

## Open Questions

1. **UVOstat API pricing** -- What does full API access cost? Is there an academic/non-profit tier?
2. **API token** -- Do you already have a UVOstat API token, or do you need to register?
3. **Target users** -- Is this for internal use (simpler UI ok) or public-facing (needs polish)?
4. **AI integration priority** -- Is the MCP server primarily for AI agent access, or is the GUI the main deliverable?
5. **Additional data sources** -- Should we integrate RPVS or CRZ data in the initial version?
6. **Deployment target** -- Local only, or cloud deployment? Docker?

---

## Sources

- [MCP Python SDK (GitHub)](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Python SDK (PyPI)](https://pypi.org/project/mcp/)
- [Build an MCP server (official docs)](https://modelcontextprotocol.io/docs/develop/build-server)
- [MCP Best Practices - Phil Schmid](https://www.philschmid.de/mcp-best-practices)
- [REST API to MCP Server Guide](https://mcpshowcase.com/blog/rest-api-to-python-mcp-server)
- [From REST API to MCP Server - Stainless](https://www.stainless.com/mcp/from-rest-api-to-mcp-server)
- [FastMCP (GitHub)](https://github.com/jlowin/fastmcp)
- [UVOstat API Docs (GitHub)](https://github.com/MiroBabic/uvostat_api)
- [UVOstat API](https://www.uvostat.sk/api)
- [datagouv-mcp](https://github.com/datagouv/datagouv-mcp)
- [mcp-civic-data](https://github.com/EricGrill/mcp-civic-data)
- [us-gov-open-data-mcp](https://github.com/lzinga/us-gov-open-data-mcp)
- [MCP-UI](https://mcpui.dev/)
- [Reflex Framework](https://reflex.dev/)
- [Reflex vs Streamlit comparison](https://reflex.dev/blog/2025-08-20-reflex-streamlit/)
- [RPVS Open Data API](https://rpvs.gov.sk/opendatav2/swagger)
- [ekosystem.slovensko.digital](https://ekosystem.slovensko.digital/)
- [Open Contracting in Slovakia](https://odimpact.org/case-open-contracting-and-procurement-in-slovakia.html)
- [Anthropic MCP Course](https://anthropic.skilljar.com/introduction-to-model-context-protocol)
- [Real Python MCP Tutorial](https://realpython.com/python-mcp/)
