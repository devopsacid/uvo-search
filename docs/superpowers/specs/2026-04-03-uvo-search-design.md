# UVO Search -- Design Specification

**Date:** 2026-04-03
**Version:** 1.0
**Status:** Ready for review

---

## Table of Contents

1. [Overview and Goals](#1-overview-and-goals)
2. [Architecture](#2-architecture)
3. [MCP Server Design](#3-mcp-server-design)
4. [NiceGUI Frontend Design](#4-nicegui-frontend-design)
5. [Data Model](#5-data-model)
6. [Configuration and Environment](#6-configuration-and-environment)
7. [Deployment](#7-deployment)
8. [Testing Strategy](#8-testing-strategy)
9. [Phased Implementation Roadmap](#9-phased-implementation-roadmap)
10. [Risks and Mitigations](#10-risks-and-mitigations)

---

## 1. Overview and Goals

### Purpose

UVO Search is a Python application for searching, browsing, and analyzing Slovak government procurement data. It provides both a programmatic interface (MCP server) for AI agents and a web interface (NiceGUI) for human users.

### Target Users

- **Journalists** investigating public spending patterns, supplier relationships, and contract awards
- **Researchers** studying procurement trends, market concentration, and policy effectiveness
- **Businesses** monitoring procurement opportunities, tracking competitor awards, and identifying contracting authorities in their sector
- **Civic watchdogs** cross-referencing beneficial ownership data with procurement winners

### Key Capabilities

- **Full-text search** across procurement titles, descriptions, and entity names
- **Structured filtering** by CPV codes (EU product classification), date ranges, contracting authorities, and suppliers
- **Detail views** showing complete procurement records with associated contracts, suppliers, and timeline
- **Entity browsing** for contracting authorities and suppliers with their procurement history
- **Entity cross-referencing** linking procurement data with CRZ contracts, beneficial ownership (RPVS), and EU-level TED notices
- **Dual access** -- AI agents via MCP protocol, humans via web browser

### Design Principles

- **Async throughout** -- all I/O operations use async/await
- **Single source of truth** -- the MCP server is the sole data access layer; the GUI is a client
- **English API, Slovak UI** -- MCP tool names and parameters use English; the web interface uses Slovak labels
- **Graceful degradation** -- if a data source is unavailable, the application continues with reduced functionality rather than failing entirely

---

## 2. Architecture

### Two-Process Architecture

The application runs as two separate processes communicating over HTTP.

```
+-------------------+         +---------------------------+         +-------------------+
|                   |  HTTP   |                           |  HTTPS  |                   |
|  Browser          | ------> |  NiceGUI App              | ------> |  UVOstat API      |
|  (user)           |         |  (port 8080)              |         |  uvostat.sk/api   |
|                   |         |                           |         |                   |
+-------------------+         |  - Search pages           |         +-------------------+
                              |  - Entity browsers        |
                              |  - Detail views           |         +-------------------+
                              |  - @ui.refreshable state  |  HTTPS  |                   |
                              |                           | ------> |  Ekosystem        |
                              +------------+--------------+         |  Datahub API      |
                                           |                        |                   |
                                           | MCP client SDK         +-------------------+
                                           | (streamable-http)
                                           |                        +-------------------+
                              +------------v--------------+  HTTPS  |                   |
                              |                           | ------> |  TED API          |
                              |  MCP Server               |         |  (EU procurement) |
                              |  (port 8000)              |         |                   |
                              |                           |         +-------------------+
                              |  - FastMCP + tools        |
                              |  - Shared httpx client    |         +-------------------+
                              |  - Pydantic validation    |  HTTPS  |                   |
                              |  - TTL caching            | ------> |  RPVS /           |
                              |                           |         |  OpenSanctions    |
+-------------------+         +---------------------------+         +-------------------+
|                   |  stdio  |
|  Claude Desktop / | ------> |  (same MCP server binary,
|  Claude Code      |         |   stdio transport)
|                   |         |
+-------------------+         +
```

### Communication Patterns

| Path | Protocol | Purpose |
|------|----------|---------|
| Browser to NiceGUI | HTTP/WebSocket (port 8080) | UI rendering, user interactions |
| NiceGUI to MCP Server | MCP over streamable-http (port 8000) | All data queries |
| MCP Server to UVOstat | HTTPS REST | Primary procurement data |
| MCP Server to Ekosystem Datahub | HTTPS REST | CRZ contracts, legal entities |
| MCP Server to TED | HTTPS REST | EU cross-reference (anonymous) |
| MCP Server to RPVS/OpenSanctions | HTTPS REST/download | Beneficial ownership |
| Claude Desktop to MCP Server | stdio | AI agent direct access |

### Why Two Processes

1. **Independent scaling** -- the MCP server handles API calls and caching; the GUI handles WebSocket connections per user
2. **Independent deployment** -- update the GUI without touching the data layer
3. **Multiple clients** -- Claude Desktop/Code connect via stdio to the same MCP server logic; the GUI connects via HTTP
4. **Simpler debugging** -- isolate data issues from UI issues

### Technology Stack

| Component | Technology | Version | Justification |
|-----------|-----------|---------|---------------|
| Language | Python | 3.12+ | Team expertise, async ecosystem, MCP SDK support |
| Package manager | uv | latest | Fast dependency resolution, lockfile support |
| MCP framework | mcp SDK (FastMCP) | 1.x stable | Official Python SDK, decorator-based tool registration |
| HTTP transport | streamable-http | (part of mcp SDK) | Stateless HTTP for GUI client, supports concurrent requests |
| Web framework | NiceGUI | 3.9+ | FastAPI-native, built-in AG Grid and ui.table, server-side pagination, async handlers |
| HTTP client | httpx | 0.27+ | Async support, connection pooling, timeout handling |
| Validation | Pydantic | 2.x | Type-safe models, automatic JSON schema generation |
| Configuration | pydantic-settings | 2.x | Typed settings from environment variables |
| Caching | cachetools | 5.x | Simple TTLCache, no external dependencies |
| Testing | pytest + pytest-asyncio | latest | Async test support, fixtures |

---

## 3. MCP Server Design

### Project Structure

```
src/uvo_mcp/
    __init__.py
    __main__.py              # Entry point: python -m uvo_mcp
    server.py                # FastMCP server definition with lifespan
    config.py                # Settings via pydantic-settings
    client.py                # UVOstat API client class (async httpx)
    models.py                # Pydantic models for all API responses
    tools/
        __init__.py
        procurements.py      # search_completed_procurements, search_announced_procurements, get_procurement_detail
        subjects.py          # find_procurer, find_supplier, get_subject_detail
        contracts.py         # search_contracts (CRZ via Ekosystem Datahub)
    utils/
        __init__.py
        cache.py             # TTL cache wrapper
        pagination.py        # Pagination helper for offset-based APIs
```

### Server Core (`server.py`)

```python
from mcp.server.fastmcp import FastMCP
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
import httpx

from uvo_mcp.config import settings

@dataclass
class AppContext:
    http_client: httpx.AsyncClient

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    async with httpx.AsyncClient(
        base_url="https://www.uvostat.sk",
        headers={"ApiToken": settings.uvostat_api_token},
        timeout=30.0,
    ) as client:
        yield AppContext(http_client=client)

mcp = FastMCP(
    "UVO Search",
    description="Search Slovak government procurement data from UVOstat.sk and related sources",
    lifespan=app_lifespan,
    json_response=True,
)
```

### Entry Point (`__main__.py`)

```python
import sys
from uvo_mcp.server import mcp

def main():
    transport = sys.argv[1] if len(sys.argv) > 1 else "streamable-http"
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
```

Usage:
- GUI/remote access: `python -m uvo_mcp` (defaults to streamable-http on port 8000)
- Claude Desktop/Code: `python -m uvo_mcp stdio`

### Configuration (`config.py`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    uvostat_api_token: str
    uvostat_base_url: str = "https://www.uvostat.sk"
    ekosystem_base_url: str = "https://datahub.ekosystem.slovensko.digital"
    ekosystem_api_token: str = ""
    ted_base_url: str = "https://api.ted.europa.eu"
    cache_ttl_search: int = 300        # 5 minutes for search results
    cache_ttl_entity: int = 3600       # 1 hour for entity lookups
    cache_ttl_detail: int = 1800       # 30 minutes for detail views
    request_timeout: float = 30.0
    max_page_size: int = 100

    model_config = {"env_file": ".env", "env_prefix": ""}

settings = Settings()
```

### MCP Tools

#### Procurement Tools (`tools/procurements.py`)

**Tool: `search_completed_procurements`**

```python
@mcp.tool()
async def search_completed_procurements(
    ctx: Context,
    text_query: str | None = Field(
        default=None,
        description="Free-text search across procurement titles and descriptions"
    ),
    cpv_codes: list[str] | None = Field(
        default=None,
        description="CPV classification codes to filter by, e.g. ['72000000-5', '34121100-2']"
    ),
    procurer_id: str | None = Field(
        default=None,
        description="Internal ID of the contracting authority"
    ),
    supplier_ico: str | None = Field(
        default=None,
        description="ICO (8-digit company ID) of the supplier"
    ),
    date_from: str | None = Field(
        default=None,
        description="Start date for publication filter (YYYY-MM-DD)"
    ),
    date_to: str | None = Field(
        default=None,
        description="End date for publication filter (YYYY-MM-DD)"
    ),
    limit: int = Field(default=20, ge=1, le=100, description="Max results per page (1-100)"),
    offset: int = Field(default=0, ge=0, description="Pagination offset"),
) -> dict:
    """Search completed (awarded) government procurements from the Slovak UVO registry.

    Returns finalized procurement records including contract values, winning suppliers,
    CPV codes, and publication dates. Use this for historical analysis of awarded contracts.

    Examples:
    - Find IT procurements since 2024: cpv_codes=["72000000-5"], date_from="2024-01-01"
    - Find procurements by a specific entity: procurer_id="86958"
    - Find contracts won by a company: supplier_ico="35763469"
    """
```

Returns: `PaginatedResponse[Procurement]` as dict (see Data Model section).

**Tool: `search_announced_procurements`**

```python
@mcp.tool()
async def search_announced_procurements(
    ctx: Context,
    text_query: str | None = Field(default=None, description="Free-text search"),
    cpv_codes: list[str] | None = Field(default=None, description="CPV codes to filter by"),
    procurer_id: str | None = Field(default=None, description="Contracting authority ID"),
    date_from: str | None = Field(default=None, description="Announcement date from (YYYY-MM-DD)"),
    date_to: str | None = Field(default=None, description="Announcement date to (YYYY-MM-DD)"),
    limit: int = Field(default=20, ge=1, le=100, description="Max results (1-100)"),
    offset: int = Field(default=0, ge=0, description="Pagination offset"),
) -> dict:
    """Search currently announced (open) government procurements.

    Returns procurement notices that are currently accepting bids. Use this to find
    active business opportunities in Slovak public procurement.
    """
```

Returns: `PaginatedResponse[Procurement]` as dict.

**Tool: `get_procurement_detail`**

```python
@mcp.tool()
async def get_procurement_detail(
    ctx: Context,
    procurement_id: str = Field(description="The procurement ID from search results"),
) -> dict:
    """Get full details of a specific procurement including all contracts and suppliers.

    Returns the complete procurement record with associated CRZ contracts, list of
    all participating suppliers, timeline of notices, and document links.
    """
```

Returns: `ProcurementDetail` as dict, including nested contracts and suppliers.

#### Subject Tools (`tools/subjects.py`)

**Tool: `find_procurer`**

```python
@mcp.tool()
async def find_procurer(
    ctx: Context,
    name_query: str | None = Field(
        default=None,
        description="Search by contracting authority name (partial match)"
    ),
    ico: str | None = Field(
        default=None,
        description="Exact ICO (8-digit company ID) lookup"
    ),
    limit: int = Field(default=20, ge=1, le=100, description="Max results (1-100)"),
    offset: int = Field(default=0, ge=0, description="Pagination offset"),
) -> dict:
    """Find contracting authorities (obstaravatelia) in the procurement registry.

    Use this to look up government bodies, municipalities, state enterprises, and other
    public entities that issue procurement contracts. Returns entity ID, name, ICO,
    address, and procurement statistics.
    """
```

Returns: `PaginatedResponse[Subject]` as dict.

**Tool: `find_supplier`**

```python
@mcp.tool()
async def find_supplier(
    ctx: Context,
    name_query: str | None = Field(
        default=None,
        description="Search by supplier company name (partial match)"
    ),
    ico: str | None = Field(
        default=None,
        description="Exact ICO (8-digit company ID) lookup"
    ),
    limit: int = Field(default=20, ge=1, le=100, description="Max results (1-100)"),
    offset: int = Field(default=0, ge=0, description="Pagination offset"),
) -> dict:
    """Find suppliers (dodavatelia) who have won government procurement contracts.

    Use this to look up companies that participate in public procurement. Returns
    entity ID, name, ICO, address, country, and contract history summary.
    """
```

Returns: `PaginatedResponse[Subject]` as dict.

**Tool: `get_subject_detail`**

```python
@mcp.tool()
async def get_subject_detail(
    ctx: Context,
    subject_id: str = Field(description="The subject ID from find_procurer or find_supplier results"),
    include_procurements: bool = Field(
        default=True,
        description="Include list of associated procurements"
    ),
) -> dict:
    """Get full details of a contracting authority or supplier.

    Returns the entity profile including address, ICO, legal form, and optionally
    a list of all procurements they have participated in.
    """
```

Returns: `SubjectDetail` as dict.

#### Contract Tools (`tools/contracts.py`)

**Tool: `search_contracts`**

```python
@mcp.tool()
async def search_contracts(
    ctx: Context,
    text_query: str | None = Field(
        default=None,
        description="Search contract subject text"
    ),
    buyer_ico: str | None = Field(
        default=None,
        description="ICO of the contracting party (buyer/government body)"
    ),
    supplier_ico: str | None = Field(
        default=None,
        description="ICO of the supplier"
    ),
    date_from: str | None = Field(
        default=None,
        description="Contract signing date from (YYYY-MM-DD)"
    ),
    date_to: str | None = Field(
        default=None,
        description="Contract signing date to (YYYY-MM-DD)"
    ),
    min_value: float | None = Field(
        default=None,
        description="Minimum contract value in EUR"
    ),
    max_value: float | None = Field(
        default=None,
        description="Maximum contract value in EUR"
    ),
    limit: int = Field(default=20, ge=1, le=100, description="Max results (1-100)"),
    offset: int = Field(default=0, ge=0, description="Pagination offset"),
) -> dict:
    """Search government contracts from the Central Register of Contracts (CRZ).

    Data sourced from the Ekosystem.Slovensko.Digital Datahub. All Slovak government
    contracts above the legal threshold must be published in CRZ. Returns contract
    number, subject, parties, signing date, and value.
    """
```

Returns: `PaginatedResponse[Contract]` as dict.

### Tool Summary

| Tool | Endpoint | Parameters | Cache TTL |
|------|----------|------------|-----------|
| `search_completed_procurements` | `/api/ukoncene_obstaravania` | text_query, cpv_codes, procurer_id, supplier_ico, date_from, date_to, limit, offset | 5 min |
| `search_announced_procurements` | `/api/vyhlasene_obstaravania` | text_query, cpv_codes, procurer_id, date_from, date_to, limit, offset | 5 min |
| `get_procurement_detail` | `/api/ukoncene_obstaravania?id[]={id}` | procurement_id | 30 min |
| `find_procurer` | `/api/obstaravatelia` | name_query, ico, limit, offset | 1 hour |
| `find_supplier` | `/api/dodavatelia` | name_query, ico, limit, offset | 1 hour |
| `get_subject_detail` | `/api/obstaravatelia?id[]={id}` or `/api/dodavatelia?id[]={id}` | subject_id, include_procurements | 1 hour |
| `search_contracts` | Datahub `/api/data/crz/contracts` | text_query, buyer_ico, supplier_ico, date_from, date_to, min_value, max_value, limit, offset | 5 min |

### Caching Strategy (`utils/cache.py`)

```python
from cachetools import TTLCache
from hashlib import sha256
import json

class ResponseCache:
    def __init__(self, maxsize: int = 1000, ttl_search: int = 300,
                 ttl_entity: int = 3600, ttl_detail: int = 1800):
        self._search_cache = TTLCache(maxsize=maxsize, ttl=ttl_search)
        self._entity_cache = TTLCache(maxsize=maxsize, ttl=ttl_entity)
        self._detail_cache = TTLCache(maxsize=maxsize, ttl=ttl_detail)

    def _key(self, endpoint: str, params: dict) -> str:
        raw = json.dumps({"endpoint": endpoint, **params}, sort_keys=True)
        return sha256(raw.encode()).hexdigest()

    def get_search(self, endpoint: str, params: dict) -> dict | None: ...
    def set_search(self, endpoint: str, params: dict, data: dict) -> None: ...
    def get_entity(self, endpoint: str, params: dict) -> dict | None: ...
    def set_entity(self, endpoint: str, params: dict, data: dict) -> None: ...
    def get_detail(self, endpoint: str, params: dict) -> dict | None: ...
    def set_detail(self, endpoint: str, params: dict, data: dict) -> None: ...
```

Three separate TTL caches with different expiration times:
- **Search results** (5 min) -- data changes infrequently but users expect recent results
- **Entity lookups** (1 hour) -- entity data is stable
- **Detail views** (30 min) -- procurement details rarely change once published

### Pagination Helper (`utils/pagination.py`)

```python
from dataclasses import dataclass

@dataclass
class PaginationParams:
    limit: int
    offset: int

    @property
    def page(self) -> int:
        return (self.offset // self.limit) + 1

    @property
    def has_more(self) -> bool:
        # Set after response
        return self._total > self.offset + self.limit

    def next_page(self) -> "PaginationParams":
        return PaginationParams(limit=self.limit, offset=self.offset + self.limit)

def build_pagination_params(limit: int, offset: int) -> dict:
    """Build query parameters for UVOstat API pagination."""
    return {"limit": min(limit, 100), "offset": max(offset, 0)}
```

---

## 4. NiceGUI Frontend Design

### Project Structure

```
src/uvo_gui/
    __init__.py
    __main__.py              # Entry point: python -m uvo_gui
    app.py                   # NiceGUI app setup, ui.run()
    config.py                # GUI-specific settings
    mcp_client.py            # MCP client wrapper (streamable-http)
    pages/
        __init__.py
        search.py            # / -- Main search page
        procurers.py         # /procurers -- Browse contracting authorities
        suppliers.py         # /suppliers -- Browse suppliers
        detail.py            # /detail/{id} -- Procurement detail with tabs
        about.py             # /about -- About page
    components/
        __init__.py
        nav_header.py        # Shared navigation header
        search_filters.py    # Reusable search filter card
        detail_dialog.py     # Procurement detail dialog (for row clicks)
        loading.py           # Loading spinner patterns
        entity_card.py       # Subject display card
```

### Pages

#### `/` -- Main Search Page (`pages/search.py`)

The primary page with full search and filtering capabilities.

**Layout:**
```
+---------------------------------------------------------------+
|  [Navigation Header]                                          |
+---------------------------------------------------------------+
|                                                               |
|  Vyhladavanie v obstaravaniach                                |
|                                                               |
|  +-----------------------------------------------------------+|
|  | [Text search input.......................] [Hladat]        ||
|  | [Datum od] [Datum do] [CPV kody v] [Typ: Ukoncene v]      ||
|  +-----------------------------------------------------------+|
|                                                               |
|  Najdenych: 1,234 zaznamov                                    |
|  +-----------------------------------------------------------+|
|  | ID   | Nazov        | Obstaravatel  | Hodnota | Datum     ||
|  |------+--------------+---------------+---------+-----------|
|  | 4521 | Dodavka IT.. | Min. vnutra.. | 45,000  | 2026-03.. ||
|  | 4520 | Rekonstruk.. | Mesto Bratis.. | 120,000 | 2026-03.. ||
|  | ...  | ...          | ...           | ...     | ...       ||
|  +-----------------------------------------------------------+|
|  |  < 1 2 3 4 5 ... 62 >      20 per page v                 ||
|  +-----------------------------------------------------------+|
|                                                               |
+---------------------------------------------------------------+
```

**Behavior:**
- Text input triggers search on Enter or button click
- Date pickers use `ui.date_input` for calendar popup
- CPV code selector uses `ui.select` with search/filter and multiple selection
- Procurement type toggle: Completed (default) / Announced
- Results displayed in `ui.table` with server-side pagination
- Row click opens detail dialog (see components)
- URL query parameters reflect current filter state for bookmarkability

**Table columns:**

| Column | Field | Sortable | Align |
|--------|-------|----------|-------|
| ID | `id` | Yes | Left |
| Nazov | `nazov` | Yes | Left |
| Obstaravatel | `obstaravatel_nazov` | Yes | Left |
| Hodnota (EUR) | `hodnota` | Yes | Right |
| Datum | `datum_zverejnenia` | Yes | Left |
| CPV | `cpv_kod` | No | Left |
| Stav | `stav` | No | Left |

#### `/procurers` -- Contracting Authorities (`pages/procurers.py`)

Browse and search contracting authorities.

**Layout:**
```
+---------------------------------------------------------------+
|  [Navigation Header]                                          |
+---------------------------------------------------------------+
|                                                               |
|  Obstaravatelia                                               |
|                                                               |
|  +-----------------------------------------------------------+|
|  | [Nazov alebo ICO.........................] [Hladat]        ||
|  +-----------------------------------------------------------+|
|                                                               |
|  +-----------------------------------------------------------+|
|  | Nazov              | ICO      | Adresa        | Pocet     ||
|  |--------------------+----------+---------------+-----------|
|  | Ministerstvo vnu.. | 00151866 | Pribinova 2.. | 342       ||
|  | Mesto Bratislava   | 00603481 | Primacialne.. | 128       ||
|  +-----------------------------------------------------------+|
|  |  < 1 2 3 ... >                                            ||
|  +-----------------------------------------------------------+|
|                                                               |
+---------------------------------------------------------------+
```

**Behavior:**
- Search by name (partial match) or ICO (exact match)
- Row click navigates to `/detail/{subject_id}?type=procurer`

#### `/suppliers` -- Suppliers (`pages/suppliers.py`)

Identical layout to `/procurers` but queries the supplier endpoint.

#### `/detail/{id}` -- Procurement Detail (`pages/detail.py`)

Full procurement detail with tabbed sections.

**Layout:**
```
+---------------------------------------------------------------+
|  [Navigation Header]                                          |
+---------------------------------------------------------------+
|                                                               |
|  Dodavka IT vybavenia pre Ministerstvo vnutra SR              |
|  Stav: Ukoncene  |  Datum: 2026-03-15  |  CPV: 72000000-5    |
|                                                               |
|  +-----------------------------------------------------------+|
|  | [Prehlad] [Zmluvy] [Dodavatelia] [Casova os]              ||
|  +-----------------------------------------------------------+|
|  |                                                           ||
|  |  (Tab content based on selection)                         ||
|  |                                                           ||
|  |  PREHLAD:                                                 ||
|  |  Obstaravatel:     Ministerstvo vnutra SR                 ||
|  |  ICO:              00151866                               ||
|  |  Predpokladana hodnota: 50,000 EUR                       ||
|  |  Konecna hodnota:       45,230 EUR                        ||
|  |  Typ postupu:     Verejna sutaz                           ||
|  |  Vestnik cislo:   123/2026                                ||
|  |  Oznamenie cislo: 4521                                    ||
|  |                                                           ||
|  +-----------------------------------------------------------+|
|                                                               |
+---------------------------------------------------------------+
```

**Tabs:**
1. **Prehlad (Overview)** -- key-value grid of all procurement fields
2. **Zmluvy (Contracts)** -- AG Grid table of associated CRZ contracts
3. **Dodavatelia (Suppliers)** -- cards for each supplier with name, ICO, address, contract value
4. **Casova os (Timeline)** -- chronological list of notices (announcement, award, modification)

#### `/about` -- About Page (`pages/about.py`)

Static page with:
- Application description and purpose
- Data source attributions (UVOstat.sk, Ekosystem Datahub, TED)
- Links to source data portals
- Version information

### Shared Components

#### Navigation Header (`components/nav_header.py`)

```python
def nav_header():
    with ui.header().classes('bg-blue-800 text-white'):
        with ui.row().classes('w-full max-w-screen-xl mx-auto items-center'):
            ui.label('UVO Search').classes(
                'text-xl font-bold cursor-pointer'
            ).on('click', lambda: ui.navigate.to('/'))
            ui.space()
            with ui.row().classes('gap-4'):
                ui.link('Vyhladavanie', '/').classes('text-white')
                ui.link('Obstaravatelia', '/procurers').classes('text-white')
                ui.link('Dodavatelia', '/suppliers').classes('text-white')
                ui.link('O aplikacii', '/about').classes('text-white')
```

Present on all pages. Links highlight the active page.

#### Search Filter Card (`components/search_filters.py`)

Reusable filter form used on `/`, `/procurers`, and `/suppliers`.

```python
class SearchFilters:
    def __init__(self, on_search: Callable, show_dates: bool = True,
                 show_cpv: bool = True, show_type_toggle: bool = True):
        self.query = ''
        self.date_from = ''
        self.date_to = ''
        self.cpv_codes: list[str] = []
        self.procurement_type = 'completed'
        self.on_search = on_search
        # ... build UI in __init__

    def render(self) -> None:
        with ui.card().classes('w-full mb-4'):
            with ui.row().classes('w-full items-end gap-4 flex-wrap'):
                # text input, date pickers, CPV select, search button
                ...
```

#### Detail Dialog (`components/detail_dialog.py`)

Modal dialog opened on row click in search results. Shows a summary of the procurement with a "View full detail" button that navigates to `/detail/{id}`.

```python
async def show_detail_dialog(procurement: dict) -> None:
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
        ui.label(procurement.get('nazov', '')).classes('text-xl font-bold')
        ui.separator()
        with ui.grid(columns=2).classes('w-full gap-2'):
            # Key fields: obstaravatel, hodnota, datum, cpv, stav
            ...
        with ui.row().classes('w-full justify-end mt-4'):
            ui.button('Zavriet', on_click=dialog.close)
            ui.button('Detail', on_click=lambda: ui.navigate.to(
                f"/detail/{procurement['id']}"
            ))
    dialog.open()
```

#### Loading Spinner (`components/loading.py`)

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def loading_container(container: ui.element):
    """Replace container content with spinner during async operation."""
    container.clear()
    with container:
        ui.spinner('dots', size='xl').classes('mx-auto my-8')
    try:
        yield container
    finally:
        pass  # caller is responsible for populating container
```

### State Management

Each page uses a `SearchState` class pattern combined with `@ui.refreshable`:

```python
class SearchState:
    def __init__(self):
        self.query: str = ''
        self.date_from: str = ''
        self.date_to: str = ''
        self.cpv_codes: list[str] = []
        self.results: list[dict] = []
        self.total: int = 0
        self.page: int = 1
        self.per_page: int = 20
        self.loading: bool = False
        self.error: str | None = None

    async def search(self) -> None:
        self.page = 1
        self.loading = True
        self.error = None
        self.results_view.refresh()
        try:
            data = await mcp_client.call_tool(
                'search_completed_procurements',
                {
                    'text_query': self.query or None,
                    'date_from': self.date_from or None,
                    'date_to': self.date_to or None,
                    'cpv_codes': self.cpv_codes or None,
                    'limit': self.per_page,
                    'offset': 0,
                },
            )
            self.results = data['data']
            self.total = data['summary']['total_records']
        except Exception as e:
            self.error = str(e)
            self.results = []
        finally:
            self.loading = False
            self.results_view.refresh()

    @ui.refreshable
    def results_view(self) -> None:
        if self.loading:
            ui.spinner('dots', size='xl').classes('mx-auto my-8')
            return
        if self.error:
            ui.label(f'Chyba: {self.error}').classes('text-red-500')
            return
        if not self.results:
            ui.label('Ziadne vysledky').classes('text-gray-500')
            return
        # Render ui.table with server-side pagination
        ...
```

State is per-page-instance (not shared across tabs). The NiceGUI storage system (`app.storage.user`) is used for persistent user preferences like rows-per-page setting.

### MCP Client Wrapper (`mcp_client.py`)

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from uvo_gui.config import settings
import json

async def call_tool(tool_name: str, arguments: dict) -> dict:
    """Call an MCP tool on the server and return the parsed result."""
    async with streamablehttp_client(settings.mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            # result.content is a list of TextContent or other content types
            for content in result.content:
                if hasattr(content, 'text'):
                    return json.loads(content.text)
            raise ValueError(f"No text content in response from {tool_name}")
```

---

## 5. Data Model

### Core Pydantic Models (`models.py`)

```python
from pydantic import BaseModel, Field
from datetime import date
from typing import Generic, TypeVar

T = TypeVar("T")


class PaginationSummary(BaseModel):
    total_records: int = Field(description="Total matching records across all pages")
    offset: int = Field(description="Current offset")
    limit: int = Field(description="Page size")


class PaginatedResponse(BaseModel, Generic[T]):
    summary: PaginationSummary
    data: list[T]


class Procurement(BaseModel):
    id: str = Field(description="Internal procurement ID")
    nazov: str = Field(description="Procurement title")
    popis: str | None = Field(default=None, description="Description text")
    obstaravatel_id: str | None = Field(default=None, description="Contracting authority ID")
    obstaravatel_nazov: str | None = Field(default=None, description="Contracting authority name")
    obstaravatel_ico: str | None = Field(default=None, description="Contracting authority ICO")
    predpokladana_hodnota: float | None = Field(default=None, description="Estimated value in EUR")
    konecna_hodnota: float | None = Field(default=None, description="Final awarded value in EUR")
    mena: str = Field(default="EUR", description="Currency code")
    datum_vyhlasenia: date | None = Field(default=None, description="Announcement date")
    datum_zverejnenia: date | None = Field(default=None, description="Publication date")
    datum_ukoncenia: date | None = Field(default=None, description="Closing date")
    cpv_kod: str | None = Field(default=None, description="Primary CPV code")
    cpv_kody: list[str] = Field(default_factory=list, description="All CPV codes")
    stav: str | None = Field(default=None, description="Status: vyhlasene, ukoncene, zrusene")
    typ_postupu: str | None = Field(default=None, description="Procedure type")
    vestnik_cislo: str | None = Field(default=None, description="Bulletin issue number")
    oznamenie_cislo: str | None = Field(default=None, description="Notice number")
    dodavatelia: list["SupplierSummary"] = Field(
        default_factory=list, description="Winning suppliers"
    )


class SupplierSummary(BaseModel):
    id: str | None = Field(default=None, description="Internal supplier ID")
    nazov: str = Field(description="Supplier name")
    ico: str | None = Field(default=None, description="ICO (8-digit company ID)")
    hodnota: float | None = Field(default=None, description="Contract value for this supplier")


class Subject(BaseModel):
    id: str = Field(description="Internal subject ID")
    nazov: str = Field(description="Entity name")
    ico: str | None = Field(default=None, description="ICO (8-digit company ID)")
    dic: str | None = Field(default=None, description="Tax ID")
    adresa: str | None = Field(default=None, description="Full address")
    typ: str | None = Field(
        default=None, description="Entity type: obstaravatel or dodavatel"
    )
    pravna_forma: str | None = Field(default=None, description="Legal form")
    krajina: str | None = Field(default=None, description="Country code")
    pocet_obstaravani: int | None = Field(
        default=None, description="Number of associated procurements"
    )
    celkova_hodnota: float | None = Field(
        default=None, description="Total procurement value in EUR"
    )


class SubjectDetail(Subject):
    obstaravania: list[Procurement] = Field(
        default_factory=list, description="Associated procurements"
    )


class ProcurementDetail(Procurement):
    zmluvy: list["Contract"] = Field(
        default_factory=list, description="Associated CRZ contracts"
    )
    oznamenia: list["Notice"] = Field(
        default_factory=list, description="Published notices/announcements"
    )


class Contract(BaseModel):
    id: str = Field(description="CRZ contract ID")
    cislo: str | None = Field(default=None, description="Contract number")
    predmet: str = Field(description="Contract subject")
    objednavatel_nazov: str | None = Field(default=None, description="Buyer name")
    objednavatel_ico: str | None = Field(default=None, description="Buyer ICO")
    dodavatel_nazov: str | None = Field(default=None, description="Supplier name")
    dodavatel_ico: str | None = Field(default=None, description="Supplier ICO")
    datum_podpisu: date | None = Field(default=None, description="Signing date")
    datum_ucinnosti: date | None = Field(default=None, description="Effective date")
    datum_platnosti: date | None = Field(default=None, description="Validity end date")
    celkova_hodnota: float | None = Field(default=None, description="Total value in EUR")
    mena: str = Field(default="EUR", description="Currency code")


class Notice(BaseModel):
    id: str = Field(description="Notice ID")
    typ: str = Field(description="Notice type (vyhlasenie, vysledok, zmena, zrusenie)")
    vestnik_cislo: str | None = Field(default=None, description="Bulletin issue")
    datum_zverejnenia: date | None = Field(default=None, description="Publication date")
    url: str | None = Field(default=None, description="Link to full notice on UVO.gov.sk")


class CPVCode(BaseModel):
    kod: str = Field(description="CPV code, e.g. '72000000-5'")
    nazov: str = Field(description="CPV code description")
    uroven: str | None = Field(
        default=None, description="Hierarchy level: division, group, class, category"
    )
    nadradeny_kod: str | None = Field(default=None, description="Parent CPV code")
```

### Entity Relationships

```
Subject (obstaravatel) ----1:N----> Procurement
Procurement ----N:M----> Subject (dodavatel)  [via SupplierSummary]
Procurement ----1:N----> Contract (CRZ)
Procurement ----1:N----> Notice
Procurement ----N:M----> CPVCode
```

---

## 6. Configuration and Environment

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `UVOSTAT_API_TOKEN` | Yes | -- | API token for UVOstat.sk |
| `UVOSTAT_BASE_URL` | No | `https://www.uvostat.sk` | UVOstat API base URL |
| `EKOSYSTEM_BASE_URL` | No | `https://datahub.ekosystem.slovensko.digital` | Ekosystem Datahub base URL |
| `EKOSYSTEM_API_TOKEN` | No | `""` | Ekosystem Datahub API token (empty = unauthenticated) |
| `TED_BASE_URL` | No | `https://api.ted.europa.eu` | TED API base URL |
| `MCP_SERVER_URL` | No | `http://localhost:8000/mcp` | MCP server URL (for GUI) |
| `STORAGE_SECRET` | Yes | -- | NiceGUI storage encryption secret |
| `CACHE_TTL_SEARCH` | No | `300` | TTL in seconds for search result cache |
| `CACHE_TTL_ENTITY` | No | `3600` | TTL in seconds for entity lookup cache |
| `CACHE_TTL_DETAIL` | No | `1800` | TTL in seconds for detail view cache |
| `REQUEST_TIMEOUT` | No | `30.0` | HTTP request timeout in seconds |
| `GUI_HOST` | No | `0.0.0.0` | NiceGUI bind host |
| `GUI_PORT` | No | `8080` | NiceGUI bind port |
| `MCP_HOST` | No | `0.0.0.0` | MCP server bind host |
| `MCP_PORT` | No | `8000` | MCP server bind port |
| `LOG_LEVEL` | No | `INFO` | Logging level |

### `.env.example`

```bash
# Required
UVOSTAT_API_TOKEN=your-token-here
STORAGE_SECRET=change-this-to-a-random-string

# Optional -- data sources
EKOSYSTEM_API_TOKEN=
TED_BASE_URL=https://api.ted.europa.eu

# Optional -- networking
MCP_SERVER_URL=http://localhost:8000/mcp
GUI_HOST=0.0.0.0
GUI_PORT=8080
MCP_HOST=0.0.0.0
MCP_PORT=8000

# Optional -- caching
CACHE_TTL_SEARCH=300
CACHE_TTL_ENTITY=3600
CACHE_TTL_DETAIL=1800

# Optional -- general
REQUEST_TIMEOUT=30.0
LOG_LEVEL=INFO
```

### `.gitignore` entries

```
.env
*.pyc
__pycache__/
.nicegui/
```

---

## 7. Deployment

### Docker Compose

```yaml
services:
  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile.mcp
    ports:
      - "8000:8000"
    environment:
      - UVOSTAT_API_TOKEN=${UVOSTAT_API_TOKEN}
      - EKOSYSTEM_API_TOKEN=${EKOSYSTEM_API_TOKEN}
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8000
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    restart: unless-stopped

  gui:
    build:
      context: .
      dockerfile: Dockerfile.gui
    ports:
      - "8080:8080"
    environment:
      - MCP_SERVER_URL=http://mcp-server:8000/mcp
      - STORAGE_SECRET=${STORAGE_SECRET}
      - GUI_HOST=0.0.0.0
      - GUI_PORT=8080
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    volumes:
      - nicegui-storage:/app/.nicegui
    depends_on:
      mcp-server:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8080/')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    restart: unless-stopped

volumes:
  nicegui-storage:
```

### Dockerfiles

**`Dockerfile.mcp`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY src/uvo_mcp/ src/uvo_mcp/

EXPOSE 8000
CMD ["uv", "run", "python", "-m", "uvo_mcp"]
```

**`Dockerfile.gui`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY src/uvo_gui/ src/uvo_gui/

EXPOSE 8080
CMD ["uv", "run", "python", "-m", "uvo_gui"]
```

### Health Check Endpoints

The MCP server exposes a health endpoint via FastAPI (the FastMCP server runs on FastAPI internally):

```python
# Added to server.py or as a FastAPI route
@app.get("/health")
async def health():
    return {"status": "ok", "service": "uvo-mcp"}
```

The NiceGUI app's root page (`/`) serves as its health indicator. Alternatively, add:

```python
@app.get("/health")
async def health():
    return {"status": "ok", "service": "uvo-gui"}
```

### Volume: `nicegui-storage`

NiceGUI stores user session data (saved searches, preferences) in `.nicegui/` by default. The Docker volume ensures this persists across container restarts.

---

## 8. Testing Strategy

### Test Structure

```
tests/
    conftest.py                  # Shared fixtures: mock httpx, MCP client
    mcp/
        test_tools_procurements.py
        test_tools_subjects.py
        test_tools_contracts.py
        test_client.py
        test_cache.py
        test_models.py
    gui/
        test_search_page.py
        test_detail_page.py
        test_mcp_client.py
    integration/
        test_uvostat_api.py      # Real API tests (gated)
        test_mcp_gui_flow.py     # End-to-end MCP + GUI
```

### MCP Server Tests

Tools are tested by mocking the `httpx.AsyncClient` responses. Each test verifies:
- Correct API endpoint is called with expected parameters
- Response is parsed into the correct Pydantic model
- Pagination metadata is preserved
- Error cases return structured error dicts (not exceptions)

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from uvo_mcp.server import AppContext

@pytest.fixture
def mock_http_client():
    client = AsyncMock(spec=httpx.AsyncClient)
    return client

@pytest.fixture
def mock_context(mock_http_client):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = AppContext(http_client=mock_http_client)
    return ctx
```

```python
# tests/mcp/test_tools_procurements.py
import pytest
from uvo_mcp.tools.procurements import search_completed_procurements

@pytest.mark.asyncio
async def test_search_completed_basic(mock_context, mock_http_client):
    mock_http_client.get.return_value = MockResponse(200, {
        "summary": {"total_records": 1, "offset": 0, "limit": 20},
        "data": [{"id": "123", "nazov": "Test procurement"}],
    })

    result = await search_completed_procurements(
        ctx=mock_context, limit=20, offset=0
    )

    assert result["summary"]["total_records"] == 1
    assert len(result["data"]) == 1
    mock_http_client.get.assert_called_once_with(
        "/api/ukoncene_obstaravania",
        params={"limit": 20, "offset": 0},
    )

@pytest.mark.asyncio
async def test_search_completed_with_filters(mock_context, mock_http_client):
    mock_http_client.get.return_value = MockResponse(200, {
        "summary": {"total_records": 5, "offset": 0, "limit": 20},
        "data": [...],
    })

    result = await search_completed_procurements(
        ctx=mock_context,
        cpv_codes=["72000000-5"],
        date_from="2024-01-01",
        limit=20,
        offset=0,
    )

    call_params = mock_http_client.get.call_args[1]["params"]
    assert call_params["cpv[]"] == ["72000000-5"]
    assert call_params["datum_zverejnenia_od"] == "2024-01-01"

@pytest.mark.asyncio
async def test_search_completed_api_error(mock_context, mock_http_client):
    mock_http_client.get.side_effect = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=MockResponse(500, {})
    )

    result = await search_completed_procurements(
        ctx=mock_context, limit=20, offset=0
    )

    assert "error" in result
    assert result["status_code"] == 500
```

### GUI Tests

NiceGUI provides `ui.run_with` for testing integration with FastAPI's test client:

```python
# tests/gui/test_search_page.py
import pytest
from httpx import AsyncClient, ASGITransport
from nicegui import ui, app
from uvo_gui.pages.search import search_page

@pytest.fixture
def client():
    # Register the page
    search_page()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")

@pytest.mark.asyncio
async def test_search_page_loads(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "UVO Search" in response.text
```

### Integration Tests (Optional, Gated)

```python
# tests/integration/test_uvostat_api.py
import os
import pytest
import httpx

UVOSTAT_TOKEN = os.getenv("UVOSTAT_API_TOKEN")

@pytest.mark.skipif(not UVOSTAT_TOKEN, reason="UVOSTAT_API_TOKEN not set")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_api_subjects():
    async with httpx.AsyncClient(
        base_url="https://www.uvostat.sk",
        headers={"ApiToken": UVOSTAT_TOKEN},
    ) as client:
        resp = await client.get("/api/obstaravatelia", params={"limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert len(data["data"]) <= 5
```

Run integration tests explicitly: `pytest tests/integration/ -m integration`

### Test Dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "respx>=0.22",          # httpx mock library (alternative to manual mocking)
]
```

---

## 9. Phased Implementation Roadmap

### Phase 1: MVP (3-4 days)

**Goal:** Working MCP server with core procurement tools + basic NiceGUI search page.

**MCP Server:**
- [ ] Project scaffolding: `pyproject.toml`, `src/uvo_mcp/` structure, `uv` setup
- [ ] `config.py` with pydantic-settings
- [ ] `client.py` with async httpx client for UVOstat
- [ ] `models.py` with Procurement, Subject, PaginationSummary, PaginatedResponse
- [ ] `server.py` with FastMCP, lifespan, shared httpx client
- [ ] `tools/procurements.py`: `search_completed_procurements`, `get_procurement_detail`
- [ ] `tools/subjects.py`: `find_procurer`, `find_supplier`
- [ ] Entry point with stdio + streamable-http transport support
- [ ] Health check endpoint
- [ ] Unit tests for all 4 tools with mocked HTTP responses

**NiceGUI GUI:**
- [ ] Project scaffolding: `src/uvo_gui/` structure
- [ ] `mcp_client.py` wrapper for MCP server calls
- [ ] `pages/search.py`: search input, date filters, results table with server-side pagination
- [ ] `components/nav_header.py`: basic navigation
- [ ] `components/detail_dialog.py`: row-click detail popup

**Validation criteria:**
- MCP server starts and responds to tool calls via stdio (testable with Claude Code)
- MCP server starts with streamable-http and responds to HTTP tool calls
- NiceGUI app displays search results from MCP server
- Pagination works end-to-end
- All unit tests pass

### Phase 2: Core Features (3-4 days)

**Goal:** All MCP tools implemented + multi-page GUI with detail views.

**MCP Server:**
- [ ] `tools/procurements.py`: add `search_announced_procurements`
- [ ] `tools/subjects.py`: add `get_subject_detail`
- [ ] `tools/contracts.py`: `search_contracts` via Ekosystem Datahub
- [ ] `utils/cache.py`: TTL cache with separate buckets
- [ ] `utils/pagination.py`: pagination helper
- [ ] Structured error handling for all tools (client errors, API errors, network errors)
- [ ] Unit tests for new tools and cache

**NiceGUI GUI:**
- [ ] `pages/procurers.py`: browse/search contracting authorities
- [ ] `pages/suppliers.py`: browse/search suppliers
- [ ] `pages/detail.py`: full procurement detail with tabs (overview, contracts, suppliers)
- [ ] `pages/about.py`: about page
- [ ] `components/search_filters.py`: reusable filter card with CPV selector and type toggle
- [ ] `components/entity_card.py`: subject display card
- [ ] `SearchState` class with `@ui.refreshable` pattern across all pages
- [ ] Loading spinner integration on all async operations

**Validation criteria:**
- All 7 MCP tools work and are tested
- GUI has 5 pages, all functional
- Detail page shows tabs with contracts and suppliers
- Cache reduces API calls on repeated queries
- Ekosystem Datahub contract search works

### Phase 3: Enrichment (3-5 days)

**Goal:** Cross-referencing with additional data sources.

- [ ] TED API integration: search EU-level notices for Slovak procurements above threshold
- [ ] RPVS/OpenSanctions integration: beneficial ownership lookup by ICO
- [ ] MCP tools: `search_ted_notices(country="SK", cpv_codes, date_from, date_to)`
- [ ] MCP tools: `get_beneficial_owners(ico)`
- [ ] GUI: ownership info displayed on supplier detail cards
- [ ] GUI: TED cross-reference link on procurement detail page
- [ ] GUI: export search results as CSV (download button)
- [ ] CPV code browser/selector component with hierarchical search
- [ ] Unit tests for all new tools

**Validation criteria:**
- TED search returns results for Slovak above-threshold procurements
- Beneficial ownership data displays for suppliers registered in RPVS
- CSV export downloads correctly formatted file

### Phase 4: Production (2-3 days)

**Goal:** Deployment-ready with operational concerns addressed.

- [ ] Docker Compose setup with both services
- [ ] `Dockerfile.mcp` and `Dockerfile.gui`
- [ ] Health check endpoints on both services
- [ ] Volume for NiceGUI storage persistence
- [ ] `.env.example` with all variables documented
- [ ] Logging: structured JSON logs at INFO level with request IDs
- [ ] Error handling: user-friendly error messages in GUI (not raw exceptions)
- [ ] Responsive design: test and fix on mobile viewport widths
- [ ] Rate limiting awareness: backoff on 429 responses from Ekosystem Datahub
- [ ] `pyproject.toml` finalized with all dependencies and scripts

**Validation criteria:**
- `docker compose up` starts both services and they communicate
- Health checks pass
- Application works on mobile viewport (375px width)
- Logs are structured and include request context
- Container restarts preserve user session data

---

## 10. Risks and Mitigations

### R1: UVOstat API Token Availability

**Risk:** The UVOstat API requires an `ApiToken` header. The token acquisition process is not publicly documented; it may require Patreon subscription or direct contact with the operator.

**Impact:** High -- blocks all primary data functionality.

**Mitigations:**
1. Register on UVOstat.sk and attempt to obtain a token immediately (Phase 0 prerequisite)
2. **Fallback path:** UVOstat provides a CSV bulk download at `https://www.uvostat.sk/download` (updated daily/weekly). Ingest CSV into a local SQLite database and query locally. This eliminates API dependency entirely at the cost of real-time freshness.
3. The Ekosystem Datahub provides CRZ contract data without requiring an UVOstat token -- partial functionality available regardless.

### R2: API Rate Limits

**Risk:** Ekosystem Datahub has a documented limit of 60 requests/minute per IP (unauthenticated). UVOstat rate limits are unknown.

**Impact:** Medium -- could cause request failures under sustained use.

**Mitigations:**
1. TTL cache on all read operations (5 min for searches, 1 hour for entities)
2. Exponential backoff with retry on HTTP 429 responses (max 3 retries)
3. Request deduplication: if an identical request is already in-flight, await that result rather than sending a duplicate
4. Ekosystem premium API token removes rate limits (free for research/charity use per their pricing page)

### R3: Data Freshness

**Risk:** UVOstat updates its database every 24 hours (or 7 days for lower Patreon tiers). Users may see stale data.

**Impact:** Low -- acceptable for research/analysis use cases. Not suitable for real-time bid monitoring.

**Mitigations:**
1. Display "last updated" timestamp on search results (from API response metadata if available)
2. For announced procurements where timeliness matters, link directly to UVO.gov.sk vestnik for the authoritative latest version
3. Daily sync is sufficient for all stated target user needs

### R4: MCP SDK Stability

**Risk:** The MCP Python SDK is at v1.x (stable) but the protocol is still evolving. Breaking changes could occur in minor versions.

**Impact:** Low -- v1.x API is stable and widely adopted.

**Mitigations:**
1. Pin `mcp` dependency to a specific minor version in `pyproject.toml`
2. The tool registration API (`@mcp.tool()`) is the most stable part of the SDK
3. Monitor the MCP SDK changelog before updating

### R5: NiceGUI WebSocket Scaling

**Risk:** NiceGUI maintains one WebSocket connection per browser tab. Each connection consumes server memory (1-5 MB per session).

**Impact:** Low for expected usage -- dozens to low hundreds of concurrent users.

**Mitigations:**
1. Single NiceGUI instance handles ~200-500 concurrent WebSocket connections comfortably on a 2GB RAM container
2. If scaling is needed: deploy multiple instances behind nginx with `ip_hash` sticky sessions
3. The MCP server (stateless HTTP) scales independently

### R6: External Service Availability

**Risk:** UVOstat.sk, Ekosystem Datahub, or TED API could be temporarily unavailable.

**Impact:** Medium -- partial or complete loss of search functionality.

**Mitigations:**
1. Circuit breaker pattern: after 3 consecutive failures to a data source, stop attempting for 60 seconds
2. Graceful degradation: if Ekosystem Datahub is down, contract search returns an error message but procurement search continues to work via UVOstat
3. Cache serves stale data during outages (extend TTL on failure)
4. GUI displays clear per-source status indicators rather than a generic error

---

## Appendix A: UVOstat API Endpoint Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ukoncene_obstaravania` | GET | Completed/closed procurements (2014+) |
| `/api/vyhlasene_obstaravania` | GET | Currently announced procurements |
| `/api/obstaravatelia` | GET | Contracting authorities |
| `/api/dodavatelia` | GET | Suppliers |
| `/api/crz_zmluvy` | GET | CRZ contracts (via UVOstat) |

All endpoints require `ApiToken` header. All support `limit` (max 100) and `offset` pagination.

## Appendix B: Ekosystem Datahub Endpoint Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/data/crz/contracts` | GET | CRZ contracts |
| `/api/data/crz/contracts/:id` | GET | Single contract detail |
| `/api/datahub/corporate_bodies/:id` | GET | Legal entity by ID |
| `/api/datahub/corporate_bodies/sync` | GET | Sync/delta updates |

Rate limit: 60 req/min per IP (unauthenticated). Token-based auth removes limit.

## Appendix C: File Tree Summary

```
uvo-search/
    pyproject.toml
    uv.lock
    .env.example
    .gitignore
    docker-compose.yml
    Dockerfile.mcp
    Dockerfile.gui
    README.md
    src/
        uvo_mcp/
            __init__.py
            __main__.py
            server.py
            config.py
            client.py
            models.py
            tools/
                __init__.py
                procurements.py
                subjects.py
                contracts.py
            utils/
                __init__.py
                cache.py
                pagination.py
        uvo_gui/
            __init__.py
            __main__.py
            app.py
            config.py
            mcp_client.py
            pages/
                __init__.py
                search.py
                procurers.py
                suppliers.py
                detail.py
                about.py
            components/
                __init__.py
                nav_header.py
                search_filters.py
                detail_dialog.py
                loading.py
                entity_card.py
    tests/
        conftest.py
        mcp/
            test_tools_procurements.py
            test_tools_subjects.py
            test_tools_contracts.py
            test_client.py
            test_cache.py
            test_models.py
        gui/
            test_search_page.py
            test_detail_page.py
            test_mcp_client.py
        integration/
            test_uvostat_api.py
            test_mcp_gui_flow.py
    docs/
        plan.md
        research.md
        data-sources-research.md
        nicegui-research.md
        superpowers/
            specs/
                2026-04-03-uvo-search-design.md
```
