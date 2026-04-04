# Backend (MCP Server) Documentation

## Overview

The UVO Search backend is a **FastMCP server** (Anthropic's Model Context Protocol) running on port 8000. It provides tools for searching and retrieving Slovak government procurement data from the UVOstat API.

**Key Files**:
- `src/uvo_mcp/__main__.py` — Entry point
- `src/uvo_mcp/server.py` — FastMCP server setup with httpx lifespan
- `src/uvo_mcp/config.py` — Settings (environment variables)
- `src/uvo_mcp/models.py` — Pydantic response models
- `src/uvo_mcp/tools/procurements.py` — Search and detail lookup tools
- `src/uvo_mcp/tools/subjects.py` — Procurer and supplier lookup tools

## Starting the Server

```bash
# HTTP mode (for GUI frontend)
uv run python -m uvo_mcp

# Stdio mode (for Claude Desktop/Code)
uv run python -m uvo_mcp stdio
```

The server listens on `http://0.0.0.0:8000` by default.

## Server Setup

**File**: `src/uvo_mcp/server.py`

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "UVO Search",
    instructions="Search Slovak government procurement data...",
    lifespan=app_lifespan,
    json_response=True,
    host="0.0.0.0",
    port=8000,
)
```

**Features**:
- **Lifespan Context** — Shared httpx AsyncClient for all requests
- **JSON Responses** — All tools return JSON
- **Two Transports** — HTTP (for GUI) and stdio (for Claude)
- **Health Endpoint** — `GET /health` for monitoring

### Lifespan Management

```python
@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    settings = Settings()
    async with httpx.AsyncClient(
        base_url=settings.uvostat_base_url,
        headers={"ApiToken": settings.uvostat_api_token},
        timeout=settings.request_timeout,
    ) as client:
        logger.info("MCP server starting, httpx client ready")
        yield AppContext(http_client=client, settings=settings)
        logger.info("MCP server shutting down")
```

**What it does**:
1. On startup: Create httpx AsyncClient with default headers (API token) and timeout
2. Yield context to server (available to all tools)
3. On shutdown: Close client automatically

**Why?** Single client instance for all tools avoids creating new connections on each request.

## Configuration

**File**: `src/uvo_mcp/config.py`

```python
class Settings(BaseSettings):
    uvostat_api_token: str                          # Required
    uvostat_base_url: str = "https://www.uvostat.sk"
    ekosystem_base_url: str = "https://datahub.ekosystem.slovensko.digital"
    ekosystem_api_token: str = ""
    ted_base_url: str = "https://api.ted.europa.eu"
    cache_ttl_search: int = 300
    cache_ttl_entity: int = 3600
    cache_ttl_detail: int = 1800
    request_timeout: float = 30.0
    max_page_size: int = 100
```

All settings come from environment variables (via `.env`). Unused URLs/tokens (ekosystem, ted) are for future expansion.

## Data Models

**File**: `src/uvo_mcp/models.py`

Currently defined but not used in MVP (placeholder for future use):

### PaginationSummary
```python
class PaginationSummary(BaseModel):
    total: int                  # Total number of matching records
    page: int                   # Current page number (1-based)
    page_size: int             # Records per page
    total_pages: int           # Total pages
```

### PaginatedResponse[T]
```python
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]             # Records on this page
    pagination: PaginationSummary
```

### SupplierSummary
```python
class SupplierSummary(BaseModel):
    id: str                    # Unique ID
    name: str                  # Supplier name
    ico: str | None            # Company registration number
```

### Procurement
```python
class Procurement(BaseModel):
    id: str                    # Unique ID
    name: str                  # Title
    value: float | None        # Contract value
    currency: str = "EUR"
    year: int | None
    cpv_code: str | None       # EU product category code
    contracting_authority: str | None
    suppliers: list[SupplierSummary] = []
```

### Subject
```python
class Subject(BaseModel):
    id: str
    name: str
    ico: str | None
    total_contracts: int | None
    total_value: float | None
```

**Note**: These models are defined for type clarity but the MVP returns raw UVOstat API responses (dicts). Future versions will use these models for validation and documentation.

## MCP Tools

### 1. search_completed_procurements

Search awarded government contracts from the UVOstat registry.

**Tool Name**: `search_completed_procurements`

**Parameters**:
| Name | Type | Optional | Description |
|------|------|----------|-------------|
| `text_query` | string | Yes | Full-text search (title, description) |
| `cpv_codes` | list[string] | Yes | EU product classification codes |
| `procurer_id` | string | Yes | Filter by contracting authority ID |
| `supplier_ico` | string | Yes | Filter by supplier company number (IČO) |
| `date_from` | string (YYYY-MM-DD) | Yes | Start date filter |
| `date_to` | string (YYYY-MM-DD) | Yes | End date filter |
| `limit` | int | No, default 20 | Page size (max 100) |
| `offset` | int | No, default 0 | Result offset for pagination |

**Returns**:
```json
{
  "data": [
    {
      "id": "12345",
      "nazov": "Nákup kancelárskeho vybavenia",
      "konecna_hodnota": 15000.00,
      "datum_zverejnenia": "2024-01-15",
      "obstaravatel_nazov": "Ministry of Health",
      "cpv_kod": "30100000",
      "stav": "ukončená",
      "dodavatelia": [
        {"nazov": "Company Ltd", "ico": "12345678"}
      ]
    }
  ],
  "total": 1234
}
```

**File**: `src/uvo_mcp/tools/procurements.py`

**Implementation**:
```python
@mcp.tool()
async def search_completed_procurements(
    ctx: Context,
    text_query: str | None = None,
    cpv_codes: list[str] | None = None,
    procurer_id: str | None = None,
    supplier_ico: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    app_ctx = _get_app_context(ctx)
    params = {
        "limit": min(limit, app_ctx.settings.max_page_size),
        "offset": max(offset, 0),
    }
    if text_query:
        params["text"] = text_query
    # ... map other parameters to UVOstat API query names ...
    
    response = await app_ctx.http_client.get("/api/ukoncene_obstaravania", params=params)
    response.raise_for_status()
    return response.json()
```

### 2. get_procurement_detail

Get full details of a specific procurement.

**Tool Name**: `get_procurement_detail`

**Parameters**:
| Name | Type | Optional | Description |
|------|------|----------|-------------|
| `procurement_id` | string | No | Procurement ID |

**Returns**:
```json
{
  "id": "12345",
  "nazov": "Nákup kancelárskeho vybavenia",
  "konecna_hodnota": 15000.00,
  "datum_zverejnenia": "2024-01-15",
  "obstaravatel_nazov": "Ministry of Health",
  "cpv_kod": "30100000",
  "stav": "ukončená",
  "dodavatelia": [
    {"nazov": "Company Ltd", "ico": "12345678"}
  ],
  "popis": "Long description...",
  "kriteria": [...]
}
```

**Error Response** (if not found):
```json
{
  "error": "Procurement 12345 not found",
  "status_code": 404
}
```

**Implementation**:
```python
@mcp.tool()
async def get_procurement_detail(ctx: Context, procurement_id: str) -> dict:
    app_ctx = _get_app_context(ctx)
    response = await app_ctx.http_client.get(
        "/api/ukoncene_obstaravania",
        params={"id[]": procurement_id}
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("data"):
        return {"error": f"Procurement {procurement_id} not found", "status_code": 404}
    return data["data"][0]
```

### 3. find_procurer

Search for contracting authorities (obstaravatelia) in the Slovak UVO registry.

**Tool Name**: `find_procurer`

**Parameters**:
| Name | Type | Optional | Description |
|------|------|----------|-------------|
| `name_query` | string | Yes | Full-text search by name |
| `ico` | string | Yes | Exact company registration number |
| `limit` | int | No, default 20 | Page size (max 100) |
| `offset` | int | No, default 0 | Result offset |

**Returns**:
```json
{
  "data": [
    {
      "id": "98765",
      "nazov": "Ministry of Health",
      "ico": "166698269",
      "zakazky_count": 234,
      "total_value": 50000000.00
    }
  ],
  "total": 567
}
```

**File**: `src/uvo_mcp/tools/subjects.py`

**Implementation**:
```python
@mcp.tool()
async def find_procurer(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    app_ctx = _get_app_context(ctx)
    params = {
        "limit": min(limit, app_ctx.settings.max_page_size),
        "offset": max(offset, 0),
    }
    if name_query:
        params["text"] = name_query
    if ico:
        params["ico"] = ico
    
    response = await app_ctx.http_client.get("/api/obstaravatelia", params=params)
    response.raise_for_status()
    return response.json()
```

### 4. find_supplier

Search for suppliers (awarded contractors) in the Slovak UVO registry.

**Tool Name**: `find_supplier`

**Parameters**:
| Name | Type | Optional | Description |
|------|------|----------|-------------|
| `name_query` | string | Yes | Full-text search by name |
| `ico` | string | Yes | Exact company registration number |
| `limit` | int | No, default 20 | Page size (max 100) |
| `offset` | int | No, default 0 | Result offset |

**Returns**:
```json
{
  "data": [
    {
      "id": "54321",
      "nazov": "Tech Solutions Ltd",
      "ico": "12345678",
      "zakazky_count": 89,
      "total_value": 5000000.00
    }
  ],
  "total": 1023
}
```

**Implementation**:
```python
@mcp.tool()
async def find_supplier(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    app_ctx = _get_app_context(ctx)
    params = {
        "limit": min(limit, app_ctx.settings.max_page_size),
        "offset": max(offset, 0),
    }
    if name_query:
        params["text"] = name_query
    if ico:
        params["ico"] = ico
    
    response = await app_ctx.http_client.get("/api/dodavatelia", params=params)
    response.raise_for_status()
    return response.json()
```

## Error Handling

All tools follow a consistent error pattern:

**Success** (HTTP 200):
```json
{"data": [...], "total": N}
```

**API Error** (HTTP 4xx/5xx):
```json
{
  "error": "API returned HTTP 500",
  "status_code": 500
}
```

**Connection Error** (timeout, DNS, etc):
```json
{
  "error": "Connection error: [reason]",
  "status_code": 0
}
```

**Caller must check** for `error` field in response (it's not raised as an exception).

## Health Check

**Endpoint**: `GET /health`

**Response**:
```json
{
  "status": "ok",
  "service": "uvo-mcp"
}
```

Used by Docker Compose and Kubernetes to verify the server is running.

## How to Add a New Tool

1. **Create tool function in appropriate file**:
   ```python
   # In src/uvo_mcp/tools/procurements.py (or subjects.py)
   
   @mcp.tool()
   async def my_new_tool(
       ctx: Context,
       param1: str | None = None,
       limit: int = 20,
       offset: int = 0,
   ) -> dict:
       """Search description goes here."""
       app_ctx = _get_app_context(ctx)
       
       # Build params
       params = {
           "limit": min(limit, app_ctx.settings.max_page_size),
           "offset": max(offset, 0),
       }
       if param1:
           params["field"] = param1
       
       # Call API
       try:
           response = await app_ctx.http_client.get("/api/endpoint", params=params)
           response.raise_for_status()
           return response.json()
       except httpx.HTTPStatusError as exc:
           return {
               "error": f"API returned HTTP {exc.response.status_code}",
               "status_code": exc.response.status_code,
           }
       except httpx.HTTPError as exc:
           return {"error": f"Connection error: {exc}", "status_code": 0}
   ```

2. **Tool is auto-registered**:
   - The `@mcp.tool()` decorator from server.py automatically registers it
   - Tools in `tools/procurements.py` and `tools/subjects.py` are imported in `server.py`
   - Available immediately on next server restart

3. **No configuration needed** — the tool is callable via:
   - **GUI**: `await mcp_client.call_tool("my_new_tool", {...})`
   - **Claude**: Just ask Claude to use it

## Caching (Future)

Caching is configured but not yet implemented. Configuration available:
- `CACHE_TTL_SEARCH` — Cache search results for N seconds
- `CACHE_TTL_ENTITY` — Cache procurer/supplier lookups for N seconds
- `CACHE_TTL_DETAIL` — Cache detail views for N seconds

Implementation will likely use `cachetools` (already in dependencies). See [plan.md](plan.md).

## External API Mapping

### UVOstat

**Base URL**: `https://www.uvostat.sk` (configurable via `UVOSTAT_BASE_URL`)

**Authentication**: Header `ApiToken: {UVOSTAT_API_TOKEN}`

**Endpoints**:
| Tool | Endpoint | Query Params |
|------|----------|-------------|
| `search_completed_procurements` | `/api/ukoncene_obstaravania` | `text`, `cpv[]`, `obstaravatel_id`, `dodavatel_ico`, `datum_zverejnenia_od`, `datum_zverejnenia_do`, `limit`, `offset` |
| `get_procurement_detail` | `/api/ukoncene_obstaravania` | `id[]` |
| `find_procurer` | `/api/obstaravatelia` | `text`, `ico`, `limit`, `offset` |
| `find_supplier` | `/api/dodavatelia` | `text`, `ico`, `limit`, `offset` |

### Future Integrations

- **Ekosystem Datahub** — CRZ contracts, legal entities
- **TED API** — EU-wide procurements (cross-reference)
- **RPVS/OpenSanctions** — Beneficial ownership data

See [plan.md](plan.md) and `docs/data-sources-research.md`.

## Testing

**File**: `tests/mcp/`

### Test Setup

Mock external API responses with `respx`:

```python
import respx

@pytest.mark.asyncio
async def test_search_completed_procurements():
    with respx.mock(base_url="https://www.uvostat.sk") as mock_api:
        mock_api.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "1",
                            "nazov": "Test Procurement",
                            "konecna_hodnota": 10000,
                        }
                    ],
                    "total": 1,
                },
            )
        )
        
        # Call tool (may need to mock context)
        result = await search_completed_procurements(ctx, text_query="test")
        assert result["total"] == 1
```

### Run Tests

```bash
pytest tests/mcp/ -v
```

## Logging

Tools log important events (via Python's `logging` module):

```python
logger.error("Search failed: %s", exc)
logger.info("API request to %s", endpoint)
```

Set `LOG_LEVEL` environment variable to control verbosity:
- `DEBUG` — Detailed parameter mapping, request URLs
- `INFO` — Normal operation (default)
- `WARNING` — Rate limits, slow requests
- `ERROR` — API failures
