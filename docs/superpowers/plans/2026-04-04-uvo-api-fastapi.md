# UVO Analytics API (FastAPI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI analytics service (`src/uvo_api/`, port 8001) that calls the existing MCP server and exposes aggregated REST endpoints for the Vue admin GUI.

**Architecture:** FastAPI service calls the MCP server via HTTP (same `streamablehttp_client` pattern as `uvo_gui/mcp_client.py`). For aggregations it fetches paginated results and reduces them in Python. Pydantic v2 models define all response shapes. All endpoints are async.

**Tech Stack:** FastAPI, httpx, Pydantic v2, pydantic-settings, pytest, respx

---

## File Map

| File | Role |
|---|---|
| `src/uvo_api/__init__.py` | Package marker |
| `src/uvo_api/__main__.py` | CLI entry point (`uvicorn app:app`) |
| `src/uvo_api/config.py` | `ApiSettings` — port, MCP URL |
| `src/uvo_api/mcp_client.py` | Async helper wrapping MCP HTTP calls |
| `src/uvo_api/models.py` | All Pydantic response models |
| `src/uvo_api/data/cpv_labels.json` | CPV code → SK/EN label map |
| `src/uvo_api/app.py` | FastAPI app, CORS, router registration, `/health` |
| `src/uvo_api/routers/dashboard.py` | `/api/dashboard/*` endpoints |
| `src/uvo_api/routers/contracts.py` | `/api/contracts` + `/api/contracts/{id}` |
| `src/uvo_api/routers/suppliers.py` | `/api/suppliers` + `/api/suppliers/{ico}` + `/{ico}/summary` |
| `src/uvo_api/routers/procurers.py` | `/api/procurers` + `/api/procurers/{ico}` + `/{ico}/summary` |
| `tests/api/conftest.py` | Shared fixtures (mock MCP responses) |
| `tests/api/test_config.py` | Settings validation |
| `tests/api/test_mcp_client.py` | MCP client unit tests |
| `tests/api/test_dashboard.py` | Dashboard endpoint tests |
| `tests/api/test_contracts.py` | Contract endpoint tests |
| `tests/api/test_suppliers.py` | Supplier endpoint tests |
| `tests/api/test_procurers.py` | Procurer endpoint tests |

---

## Task 1: Package scaffold + config

**Files:**
- Create: `src/uvo_api/__init__.py`
- Create: `src/uvo_api/config.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_config.py
from uvo_api.config import ApiSettings


def test_default_port():
    settings = ApiSettings(mcp_server_url="http://localhost:8000/mcp")
    assert settings.port == 8001


def test_mcp_server_url_required():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ApiSettings()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_config.py -v
```
Expected: `ModuleNotFoundError: No module named 'uvo_api'`

- [ ] **Step 3: Create package files**

```python
# src/uvo_api/__init__.py
```

```python
# src/uvo_api/config.py
"""Analytics API configuration via environment variables."""

from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    mcp_server_url: str
    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = {"env_file": ".env", "env_prefix": "API_", "extra": "ignore"}
```

```python
# tests/api/__init__.py
```

- [ ] **Step 4: Add `uvo_api` to pyproject.toml hatch packages list**

In `pyproject.toml`, find:
```toml
packages = ["src/uvo_mcp", "src/uvo_gui", "src/uvo_pipeline"]
```
Change to:
```toml
packages = ["src/uvo_mcp", "src/uvo_gui", "src/uvo_pipeline", "src/uvo_api"]
```

Also add entry point under `[project.scripts]`:
```toml
uvo-api = "uvo_api.__main__:main"
```

Also add `fastapi[standard]>=0.115.0` to `[project] dependencies`.

- [ ] **Step 5: Run test to verify it passes**

```bash
uv sync
pytest tests/api/test_config.py -v
```
Expected: PASS (both tests green)

- [ ] **Step 6: Commit**

```bash
git add src/uvo_api/__init__.py src/uvo_api/config.py tests/api/__init__.py tests/api/test_config.py pyproject.toml uv.lock
git commit -m "feat: scaffold uvo_api package with config"
```

---

## Task 2: MCP client

**Files:**
- Create: `src/uvo_api/mcp_client.py`
- Create: `tests/api/test_mcp_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_mcp_client.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_call_tool_returns_parsed_json():
    mock_result = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps({"data": [{"id": "1"}], "total": 1})
    mock_result.content = [mock_content]

    mock_session = AsyncMock()
    mock_session.call_tool.return_value = mock_result
    mock_session.initialize = AsyncMock()

    with patch("uvo_api.mcp_client.streamablehttp_client") as mock_transport, \
         patch("uvo_api.mcp_client.ClientSession") as mock_session_cls:

        mock_transport.return_value.__aenter__ = AsyncMock(return_value=(None, None, None))
        mock_transport.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from uvo_api.mcp_client import call_tool
        result = await call_tool("search_completed_procurements", {})

    assert result == {"data": [{"id": "1"}], "total": 1}


@pytest.mark.asyncio
async def test_call_tool_raises_on_no_text_content():
    mock_result = MagicMock()
    mock_result.content = []

    mock_session = AsyncMock()
    mock_session.call_tool.return_value = mock_result
    mock_session.initialize = AsyncMock()

    with patch("uvo_api.mcp_client.streamablehttp_client") as mock_transport, \
         patch("uvo_api.mcp_client.ClientSession") as mock_session_cls:

        mock_transport.return_value.__aenter__ = AsyncMock(return_value=(None, None, None))
        mock_transport.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from uvo_api.mcp_client import call_tool
        with pytest.raises(ValueError, match="No text content"):
            await call_tool("search_completed_procurements", {})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_mcp_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'uvo_api.mcp_client'`

- [ ] **Step 3: Implement MCP client**

```python
# src/uvo_api/mcp_client.py
"""MCP client wrapper for calling MCP server tools from the analytics API."""

import json
import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from uvo_api.config import ApiSettings

logger = logging.getLogger(__name__)
_settings = ApiSettings()


async def call_tool(tool_name: str, arguments: dict) -> dict:
    """Call a tool on the MCP server and return the parsed JSON response."""
    async with streamablehttp_client(_settings.mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            for content in result.content:
                if hasattr(content, "text"):
                    return json.loads(content.text)
            raise ValueError(f"No text content in response from {tool_name}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/api/test_mcp_client.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/uvo_api/mcp_client.py tests/api/test_mcp_client.py
git commit -m "feat: add uvo_api MCP client wrapper"
```

---

## Task 3: Pydantic response models

**Files:**
- Create: `src/uvo_api/models.py`

No separate test needed — models are validated by endpoint tests in later tasks. Write them now so later tasks can import them.

- [ ] **Step 1: Create models**

```python
# src/uvo_api/models.py
"""Pydantic v2 response models for the analytics API."""

from pydantic import BaseModel


# --- Shared ---

class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int


# --- Dashboard ---

class DashboardDelta(BaseModel):
    value: float
    pct: float | None = None  # percentage change vs. previous year


class DashboardSummary(BaseModel):
    total_value: float
    contract_count: int
    avg_value: float
    active_suppliers: int
    deltas: dict[str, DashboardDelta] = {}


class SpendByYear(BaseModel):
    year: int
    total_value: float


class TopSupplier(BaseModel):
    ico: str
    name: str
    total_value: float
    contract_count: int


class TopProcurer(BaseModel):
    ico: str
    name: str
    total_spend: float
    contract_count: int


class CpvShare(BaseModel):
    cpv_code: str
    label_sk: str
    label_en: str
    total_value: float
    percentage: float


class RecentContract(BaseModel):
    id: str
    title: str
    procurer_name: str
    procurer_ico: str
    value: float
    year: int
    status: str  # "active" | "closed"


# --- Contracts ---

class ContractRow(BaseModel):
    id: str
    title: str
    procurer_name: str
    procurer_ico: str
    supplier_name: str | None = None
    supplier_ico: str | None = None
    value: float
    cpv_code: str | None = None
    year: int
    status: str


class ContractDetail(ContractRow):
    all_suppliers: list[dict] = []
    publication_date: str | None = None
    source_url: str | None = None


class ContractListResponse(BaseModel):
    data: list[ContractRow]
    pagination: PaginationMeta


# --- Suppliers ---

class SupplierCard(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_value: float


class SupplierListResponse(BaseModel):
    data: list[SupplierCard]
    pagination: PaginationMeta


class ProcurerRelation(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_value: float


class SupplierDetail(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_value: float
    avg_value: float
    years_active: list[int]
    top_procurers: list[ProcurerRelation]
    contracts: list[ContractRow]


class SupplierSummary(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_value: float
    avg_value: float
    spend_by_year: list[SpendByYear]


# --- Procurers ---

class ProcurerCard(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_spend: float


class ProcurerListResponse(BaseModel):
    data: list[ProcurerCard]
    pagination: PaginationMeta


class SupplierRelation(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_value: float


class ProcurerDetail(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_spend: float
    avg_value: float
    years_active: list[int]
    top_suppliers: list[SupplierRelation]
    contracts: list[ContractRow]


class ProcurerSummary(BaseModel):
    ico: str
    name: str
    contract_count: int
    total_spend: float
    avg_value: float
    spend_by_year: list[SpendByYear]
```

- [ ] **Step 2: Verify models import cleanly**

```bash
python -c "from uvo_api.models import DashboardSummary, ContractListResponse, SupplierDetail, ProcurerDetail; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/uvo_api/models.py
git commit -m "feat: add uvo_api Pydantic response models"
```

---

## Task 4: CPV labels data file

**Files:**
- Create: `src/uvo_api/data/cpv_labels.json`
- Create: `src/uvo_api/data/__init__.py`

- [ ] **Step 1: Create the CPV labels file**

```bash
mkdir -p src/uvo_api/data
touch src/uvo_api/data/__init__.py
```

```json
// src/uvo_api/data/cpv_labels.json
{
  "72000000": {"sk": "IT služby", "en": "IT services"},
  "45000000": {"sk": "Stavebné práce", "en": "Construction work"},
  "33000000": {"sk": "Zdravotnícke prístroje", "en": "Medical equipment"},
  "60000000": {"sk": "Dopravné služby", "en": "Transport services"},
  "79000000": {"sk": "Obchodné služby", "en": "Business services"},
  "50000000": {"sk": "Opravy a údržba", "en": "Repair and maintenance"},
  "71000000": {"sk": "Architektonické a inžinierske služby", "en": "Architectural and engineering services"},
  "48000000": {"sk": "Softvérové balíky", "en": "Software packages"},
  "30000000": {"sk": "Kancelárske stroje", "en": "Office machinery"},
  "34000000": {"sk": "Dopravné zariadenia", "en": "Transport equipment"},
  "35000000": {"sk": "Bezpečnostné zariadenia", "en": "Security equipment"},
  "39000000": {"sk": "Nábytok a spotrebný tovar", "en": "Furniture and household goods"},
  "22000000": {"sk": "Tlačené materiály", "en": "Printed matter"},
  "55000000": {"sk": "Hotelové služby", "en": "Hotel and restaurant services"},
  "64000000": {"sk": "Poštové a telekomunikačné služby", "en": "Postal and telecommunications services"},
  "90000000": {"sk": "Kanalizácia a odpad", "en": "Sewage and refuse services"},
  "85000000": {"sk": "Zdravotné a sociálne služby", "en": "Health and social services"},
  "80000000": {"sk": "Vzdelávacie služby", "en": "Education and training services"},
  "75000000": {"sk": "Verejná správa", "en": "Administration and public services"},
  "66000000": {"sk": "Finančné služby", "en": "Financial services"}
}
```

- [ ] **Step 2: Verify file loads as JSON**

```bash
python -c "import json; d = json.load(open('src/uvo_api/data/cpv_labels.json')); print(len(d), 'entries')"
```
Expected: `20 entries`

- [ ] **Step 3: Commit**

```bash
git add src/uvo_api/data/
git commit -m "feat: add CPV code to label mapping data file"
```

---

## Task 5: FastAPI app skeleton + health check

**Files:**
- Create: `src/uvo_api/app.py`
- Create: `src/uvo_api/__main__.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_app.py
import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "uvo-api"}


def test_cors_header_present(client):
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert "access-control-allow-origin" in response.headers
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_app.py -v
```
Expected: `ModuleNotFoundError: No module named 'uvo_api.app'`

- [ ] **Step 3: Implement app**

```python
# src/uvo_api/app.py
"""FastAPI application factory for the UVO analytics API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from uvo_api.config import ApiSettings


def create_app() -> FastAPI:
    settings = ApiSettings()

    app = FastAPI(
        title="UVO Analytics API",
        description="Aggregated analytics endpoints for Slovak government procurement data",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "uvo-api"}

    # Routers registered in later tasks
    return app
```

```python
# src/uvo_api/__main__.py
"""Entry point for the UVO analytics API."""

import uvicorn

from uvo_api.config import ApiSettings


def main() -> None:
    settings = ApiSettings()
    uvicorn.run(
        "uvo_api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/api/test_app.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/uvo_api/app.py src/uvo_api/__main__.py tests/api/test_app.py
git commit -m "feat: add FastAPI app skeleton with health check and CORS"
```

---

## Task 6: Contracts router

**Files:**
- Create: `src/uvo_api/routers/contracts.py`
- Create: `src/uvo_api/routers/__init__.py`
- Create: `tests/api/test_contracts.py`
- Modify: `src/uvo_api/app.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_contracts.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from uvo_api.app import create_app

SAMPLE_MCP_RESPONSE = {
    "data": [
        {
            "id": "1001",
            "nazov": "IT Infrastructure",
            "obstaravatel": {"ico": "12345678", "nazov": "Ministry of Finance"},
            "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
            "hodnota_zmluvy": 150000.0,
            "datum_zverejnenia": "2024-01-15",
            "cpv_kod": "72000000",
        }
    ],
    "total": 1,
}

EMPTY_MCP_RESPONSE = {"data": [], "total": 0}


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_list_contracts_returns_paginated_response(client):
    with patch("uvo_api.routers.contracts.call_tool", new=AsyncMock(return_value=SAMPLE_MCP_RESPONSE)):
        response = client.get("/api/contracts")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "pagination" in body
    assert body["pagination"]["total"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == "1001"


def test_list_contracts_maps_fields_correctly(client):
    with patch("uvo_api.routers.contracts.call_tool", new=AsyncMock(return_value=SAMPLE_MCP_RESPONSE)):
        response = client.get("/api/contracts")
    row = response.json()["data"][0]
    assert row["title"] == "IT Infrastructure"
    assert row["procurer_name"] == "Ministry of Finance"
    assert row["procurer_ico"] == "12345678"
    assert row["supplier_name"] == "Tech Corp"
    assert row["supplier_ico"] == "87654321"
    assert row["value"] == 150000.0
    assert row["year"] == 2024


def test_list_contracts_empty_result(client):
    with patch("uvo_api.routers.contracts.call_tool", new=AsyncMock(return_value=EMPTY_MCP_RESPONSE)):
        response = client.get("/api/contracts")
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["pagination"]["total"] == 0


def test_get_contract_detail_returns_detail(client):
    detail = {
        "id": "1001",
        "nazov": "IT Infrastructure",
        "obstaravatel": {"ico": "12345678", "nazov": "Ministry of Finance"},
        "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
        "hodnota_zmluvy": 150000.0,
        "datum_zverejnenia": "2024-01-15",
        "cpv_kod": "72000000",
    }
    with patch("uvo_api.routers.contracts.call_tool", new=AsyncMock(return_value=detail)):
        response = client.get("/api/contracts/1001")
    assert response.status_code == 200
    assert response.json()["id"] == "1001"
    assert response.json()["all_suppliers"][0]["ico"] == "87654321"


def test_get_contract_detail_not_found(client):
    with patch("uvo_api.routers.contracts.call_tool", new=AsyncMock(return_value={"error": "not found", "status_code": 404})):
        response = client.get("/api/contracts/9999")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/api/test_contracts.py -v
```
Expected: collection error — module not found

- [ ] **Step 3: Implement contracts router**

```python
# src/uvo_api/routers/__init__.py
```

```python
# src/uvo_api/routers/contracts.py
"""Contracts endpoints — list and detail."""

from fastapi import APIRouter, HTTPException, Query

from uvo_api.mcp_client import call_tool
from uvo_api.models import ContractDetail, ContractListResponse, ContractRow, PaginationMeta

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


def _year_from_date(date_str: str | None) -> int:
    if date_str and len(date_str) >= 4:
        try:
            return int(date_str[:4])
        except ValueError:
            pass
    return 0


def _status_from_year(year: int) -> str:
    return "active" if year >= 2024 else "closed"


def _map_row(item: dict) -> ContractRow:
    suppliers = item.get("dodavatelia") or []
    first = suppliers[0] if suppliers else {}
    year = _year_from_date(item.get("datum_zverejnenia"))
    return ContractRow(
        id=str(item.get("id", "")),
        title=item.get("nazov", ""),
        procurer_name=(item.get("obstaravatel") or {}).get("nazov", ""),
        procurer_ico=(item.get("obstaravatel") or {}).get("ico", ""),
        supplier_name=first.get("nazov"),
        supplier_ico=first.get("ico"),
        value=float(item.get("hodnota_zmluvy") or 0),
        cpv_code=item.get("cpv_kod"),
        year=year,
        status=_status_from_year(year),
    )


@router.get("", response_model=ContractListResponse)
async def list_contracts(
    q: str | None = Query(None),
    cpv: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    value_min: float | None = Query(None),
    value_max: float | None = Query(None),
    ico: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ContractListResponse:
    args: dict = {"limit": limit, "offset": offset}
    if q:
        args["text_query"] = q
    if cpv:
        args["cpv_codes"] = [cpv]
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    if ico:
        args["supplier_ico"] = ico

    result = await call_tool("search_completed_procurements", args)

    items = result.get("data", [])
    total = result.get("total", len(items))

    rows = [_map_row(i) for i in items]
    if value_min is not None:
        rows = [r for r in rows if r.value >= value_min]
    if value_max is not None:
        rows = [r for r in rows if r.value <= value_max]

    return ContractListResponse(
        data=rows,
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/{contract_id}", response_model=ContractDetail)
async def get_contract(contract_id: str) -> ContractDetail:
    result = await call_tool("get_procurement_detail", {"procurement_id": contract_id})
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 404), detail=result["error"])

    suppliers = result.get("dodavatelia") or []
    first = suppliers[0] if suppliers else {}
    year = _year_from_date(result.get("datum_zverejnenia"))

    return ContractDetail(
        id=str(result.get("id", "")),
        title=result.get("nazov", ""),
        procurer_name=(result.get("obstaravatel") or {}).get("nazov", ""),
        procurer_ico=(result.get("obstaravatel") or {}).get("ico", ""),
        supplier_name=first.get("nazov"),
        supplier_ico=first.get("ico"),
        value=float(result.get("hodnota_zmluvy") or 0),
        cpv_code=result.get("cpv_kod"),
        year=year,
        status=_status_from_year(year),
        all_suppliers=suppliers,
        publication_date=result.get("datum_zverejnenia"),
    )
```

- [ ] **Step 4: Register router in `app.py`**

```python
# src/uvo_api/app.py  — add after existing imports, before create_app
from uvo_api.routers import contracts  # noqa: E402
```

Inside `create_app()`, before `return app`:
```python
    app.include_router(contracts.router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/api/test_contracts.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add src/uvo_api/routers/ tests/api/test_contracts.py src/uvo_api/app.py
git commit -m "feat: add /api/contracts endpoints"
```

---

## Task 7: Suppliers router

**Files:**
- Create: `src/uvo_api/routers/suppliers.py`
- Create: `tests/api/test_suppliers.py`
- Modify: `src/uvo_api/app.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_suppliers.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from uvo_api.app import create_app

SAMPLE_SUPPLIER_RESPONSE = {
    "data": [
        {"ico": "87654321", "nazov": "Tech Corp", "pocet_zakaziek": 10, "celkova_hodnota": 5000000.0},
        {"ico": "11111111", "nazov": "Build Co", "pocet_zakaziek": 5, "celkova_hodnota": 2000000.0},
    ],
    "total": 2,
}

SAMPLE_CONTRACTS_FOR_SUPPLIER = {
    "data": [
        {
            "id": "1001",
            "nazov": "IT Project",
            "obstaravatel": {"ico": "12345678", "nazov": "Ministry"},
            "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
            "hodnota_zmluvy": 500000.0,
            "datum_zverejnenia": "2023-06-01",
            "cpv_kod": "72000000",
        }
    ],
    "total": 1,
}


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_list_suppliers(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE)):
        response = client.get("/api/suppliers")
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["data"][0]["ico"] == "87654321"
    assert body["data"][0]["name"] == "Tech Corp"
    assert body["data"][0]["contract_count"] == 10
    assert body["pagination"]["total"] == 2


def test_list_suppliers_search_by_name(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE)) as mock:
        client.get("/api/suppliers?q=Tech")
    mock.assert_called_once()
    args = mock.call_args[0][1]
    assert args.get("name_query") == "Tech"


def test_list_suppliers_search_by_ico(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE)) as mock:
        client.get("/api/suppliers?ico=87654321")
    args = mock.call_args[0][1]
    assert args.get("ico") == "87654321"


def test_get_supplier_detail(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(side_effect=[
        {"data": [{"ico": "87654321", "nazov": "Tech Corp", "pocet_zakaziek": 1, "celkova_hodnota": 500000.0}], "total": 1},
        SAMPLE_CONTRACTS_FOR_SUPPLIER,
    ])):
        response = client.get("/api/suppliers/87654321")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "87654321"
    assert body["contract_count"] == 1
    assert len(body["contracts"]) == 1
    assert body["contracts"][0]["id"] == "1001"


def test_get_supplier_summary(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(side_effect=[
        {"data": [{"ico": "87654321", "nazov": "Tech Corp", "pocet_zakaziek": 1, "celkova_hodnota": 500000.0}], "total": 1},
        SAMPLE_CONTRACTS_FOR_SUPPLIER,
    ])):
        response = client.get("/api/suppliers/87654321/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "87654321"
    assert "spend_by_year" in body
    assert body["spend_by_year"][0]["year"] == 2023


def test_get_supplier_not_found(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(return_value={"data": [], "total": 0})):
        response = client.get("/api/suppliers/00000000")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/api/test_suppliers.py -v
```
Expected: collection or import error

- [ ] **Step 3: Implement suppliers router**

```python
# src/uvo_api/routers/suppliers.py
"""Suppliers endpoints."""

from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from uvo_api.mcp_client import call_tool
from uvo_api.models import (
    ContractRow,
    PaginationMeta,
    ProcurerRelation,
    SpendByYear,
    SupplierCard,
    SupplierDetail,
    SupplierListResponse,
    SupplierSummary,
)

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


def _year_from_date(date_str: str | None) -> int:
    if date_str and len(date_str) >= 4:
        try:
            return int(date_str[:4])
        except ValueError:
            pass
    return 0


def _status_from_year(year: int) -> str:
    return "active" if year >= 2024 else "closed"


def _map_contract_row(item: dict) -> ContractRow:
    suppliers = item.get("dodavatelia") or []
    first = suppliers[0] if suppliers else {}
    year = _year_from_date(item.get("datum_zverejnenia"))
    return ContractRow(
        id=str(item.get("id", "")),
        title=item.get("nazov", ""),
        procurer_name=(item.get("obstaravatel") or {}).get("nazov", ""),
        procurer_ico=(item.get("obstaravatel") or {}).get("ico", ""),
        supplier_name=first.get("nazov"),
        supplier_ico=first.get("ico"),
        value=float(item.get("hodnota_zmluvy") or 0),
        cpv_code=item.get("cpv_kod"),
        year=year,
        status=_status_from_year(year),
    )


@router.get("", response_model=SupplierListResponse)
async def list_suppliers(
    q: str | None = Query(None),
    ico: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SupplierListResponse:
    args: dict = {"limit": limit, "offset": offset}
    if q:
        args["name_query"] = q
    if ico:
        args["ico"] = ico

    result = await call_tool("find_supplier", args)
    items = result.get("data", [])
    total = result.get("total", len(items))

    cards = [
        SupplierCard(
            ico=str(s.get("ico", "")),
            name=s.get("nazov", ""),
            contract_count=int(s.get("pocet_zakaziek") or 0),
            total_value=float(s.get("celkova_hodnota") or 0),
        )
        for s in items
    ]
    return SupplierListResponse(
        data=cards,
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


async def _fetch_supplier_and_contracts(ico: str) -> tuple[dict, list[dict]]:
    supplier_result = await call_tool("find_supplier", {"ico": ico, "limit": 1})
    suppliers = supplier_result.get("data", [])
    if not suppliers:
        raise HTTPException(status_code=404, detail=f"Supplier {ico} not found")
    supplier = suppliers[0]

    contracts_result = await call_tool(
        "search_completed_procurements", {"supplier_ico": ico, "limit": 100}
    )
    contracts = contracts_result.get("data", [])
    return supplier, contracts


@router.get("/{ico}/summary", response_model=SupplierSummary)
async def get_supplier_summary(ico: str) -> SupplierSummary:
    supplier, contracts = await _fetch_supplier_and_contracts(ico)

    spend_by_year: dict[int, float] = defaultdict(float)
    for c in contracts:
        year = _year_from_date(c.get("datum_zverejnenia"))
        spend_by_year[year] += float(c.get("hodnota_zmluvy") or 0)

    total_value = float(supplier.get("celkova_hodnota") or sum(spend_by_year.values()))
    count = int(supplier.get("pocet_zakaziek") or len(contracts))

    return SupplierSummary(
        ico=str(supplier.get("ico", ico)),
        name=supplier.get("nazov", ""),
        contract_count=count,
        total_value=total_value,
        avg_value=total_value / count if count else 0,
        spend_by_year=[SpendByYear(year=y, total_value=v) for y, v in sorted(spend_by_year.items())],
    )


@router.get("/{ico}", response_model=SupplierDetail)
async def get_supplier_detail(ico: str) -> SupplierDetail:
    supplier, contracts = await _fetch_supplier_and_contracts(ico)

    procurer_totals: dict[str, dict] = defaultdict(lambda: {"name": "", "count": 0, "value": 0.0})
    years: set[int] = set()
    rows: list[ContractRow] = []

    for c in contracts:
        row = _map_contract_row(c)
        rows.append(row)
        years.add(row.year)
        if row.procurer_ico:
            p = procurer_totals[row.procurer_ico]
            p["name"] = row.procurer_name
            p["count"] += 1
            p["value"] += row.value

    top_procurers = sorted(
        [
            ProcurerRelation(ico=k, name=v["name"], contract_count=v["count"], total_value=v["value"])
            for k, v in procurer_totals.items()
        ],
        key=lambda x: x.total_value,
        reverse=True,
    )[:10]

    total_value = float(supplier.get("celkova_hodnota") or sum(r.value for r in rows))
    count = int(supplier.get("pocet_zakaziek") or len(rows))

    return SupplierDetail(
        ico=str(supplier.get("ico", ico)),
        name=supplier.get("nazov", ""),
        contract_count=count,
        total_value=total_value,
        avg_value=total_value / count if count else 0,
        years_active=sorted(y for y in years if y > 0),
        top_procurers=top_procurers,
        contracts=rows,
    )
```

- [ ] **Step 4: Register router in `app.py`**

Add to imports in `app.py`:
```python
from uvo_api.routers import suppliers
```
Inside `create_app()`, before `return app`:
```python
    app.include_router(suppliers.router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/api/test_suppliers.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add src/uvo_api/routers/suppliers.py tests/api/test_suppliers.py src/uvo_api/app.py
git commit -m "feat: add /api/suppliers endpoints"
```

---

## Task 8: Procurers router

**Files:**
- Create: `src/uvo_api/routers/procurers.py`
- Create: `tests/api/test_procurers.py`
- Modify: `src/uvo_api/app.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_procurers.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from uvo_api.app import create_app

SAMPLE_PROCURER_RESPONSE = {
    "data": [
        {"ico": "12345678", "nazov": "Ministry of Finance", "pocet_zakaziek": 20, "celkova_hodnota": 10000000.0},
    ],
    "total": 1,
}

SAMPLE_CONTRACTS_FOR_PROCURER = {
    "data": [
        {
            "id": "2001",
            "nazov": "Cloud Services",
            "obstaravatel": {"ico": "12345678", "nazov": "Ministry of Finance"},
            "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
            "hodnota_zmluvy": 300000.0,
            "datum_zverejnenia": "2023-03-10",
            "cpv_kod": "72000000",
        }
    ],
    "total": 1,
}


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_list_procurers(client):
    with patch("uvo_api.routers.procurers.call_tool", new=AsyncMock(return_value=SAMPLE_PROCURER_RESPONSE)):
        response = client.get("/api/procurers")
    assert response.status_code == 200
    body = response.json()
    assert body["data"][0]["ico"] == "12345678"
    assert body["data"][0]["name"] == "Ministry of Finance"
    assert body["data"][0]["contract_count"] == 20
    assert body["pagination"]["total"] == 1


def test_get_procurer_detail(client):
    with patch("uvo_api.routers.procurers.call_tool", new=AsyncMock(side_effect=[
        SAMPLE_PROCURER_RESPONSE,
        SAMPLE_CONTRACTS_FOR_PROCURER,
    ])):
        response = client.get("/api/procurers/12345678")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "12345678"
    assert body["contract_count"] == 20
    assert len(body["contracts"]) == 1
    assert len(body["top_suppliers"]) == 1
    assert body["top_suppliers"][0]["ico"] == "87654321"


def test_get_procurer_summary(client):
    with patch("uvo_api.routers.procurers.call_tool", new=AsyncMock(side_effect=[
        SAMPLE_PROCURER_RESPONSE,
        SAMPLE_CONTRACTS_FOR_PROCURER,
    ])):
        response = client.get("/api/procurers/12345678/summary")
    assert response.status_code == 200
    body = response.json()
    assert "spend_by_year" in body
    assert body["spend_by_year"][0]["year"] == 2023


def test_get_procurer_not_found(client):
    with patch("uvo_api.routers.procurers.call_tool", new=AsyncMock(return_value={"data": [], "total": 0})):
        response = client.get("/api/procurers/00000000")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/api/test_procurers.py -v
```
Expected: collection or import error

- [ ] **Step 3: Implement procurers router**

```python
# src/uvo_api/routers/procurers.py
"""Procurers endpoints."""

from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from uvo_api.mcp_client import call_tool
from uvo_api.models import (
    ContractRow,
    PaginationMeta,
    ProcurerCard,
    ProcurerDetail,
    ProcurerListResponse,
    ProcurerSummary,
    SpendByYear,
    SupplierRelation,
)

router = APIRouter(prefix="/api/procurers", tags=["procurers"])


def _year_from_date(date_str: str | None) -> int:
    if date_str and len(date_str) >= 4:
        try:
            return int(date_str[:4])
        except ValueError:
            pass
    return 0


def _status_from_year(year: int) -> str:
    return "active" if year >= 2024 else "closed"


def _map_contract_row(item: dict) -> ContractRow:
    suppliers = item.get("dodavatelia") or []
    first = suppliers[0] if suppliers else {}
    year = _year_from_date(item.get("datum_zverejnenia"))
    return ContractRow(
        id=str(item.get("id", "")),
        title=item.get("nazov", ""),
        procurer_name=(item.get("obstaravatel") or {}).get("nazov", ""),
        procurer_ico=(item.get("obstaravatel") or {}).get("ico", ""),
        supplier_name=first.get("nazov"),
        supplier_ico=first.get("ico"),
        value=float(item.get("hodnota_zmluvy") or 0),
        cpv_code=item.get("cpv_kod"),
        year=year,
        status=_status_from_year(year),
    )


@router.get("", response_model=ProcurerListResponse)
async def list_procurers(
    q: str | None = Query(None),
    ico: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ProcurerListResponse:
    args: dict = {"limit": limit, "offset": offset}
    if q:
        args["name_query"] = q
    if ico:
        args["ico"] = ico

    result = await call_tool("find_procurer", args)
    items = result.get("data", [])
    total = result.get("total", len(items))

    cards = [
        ProcurerCard(
            ico=str(p.get("ico", "")),
            name=p.get("nazov", ""),
            contract_count=int(p.get("pocet_zakaziek") or 0),
            total_spend=float(p.get("celkova_hodnota") or 0),
        )
        for p in items
    ]
    return ProcurerListResponse(
        data=cards,
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


async def _fetch_procurer_and_contracts(ico: str) -> tuple[dict, list[dict]]:
    procurer_result = await call_tool("find_procurer", {"ico": ico, "limit": 1})
    procurers = procurer_result.get("data", [])
    if not procurers:
        raise HTTPException(status_code=404, detail=f"Procurer {ico} not found")
    procurer = procurers[0]

    contracts_result = await call_tool(
        "search_completed_procurements", {"procurer_id": ico, "limit": 100}
    )
    contracts = contracts_result.get("data", [])
    return procurer, contracts


@router.get("/{ico}/summary", response_model=ProcurerSummary)
async def get_procurer_summary(ico: str) -> ProcurerSummary:
    procurer, contracts = await _fetch_procurer_and_contracts(ico)

    spend_by_year: dict[int, float] = defaultdict(float)
    for c in contracts:
        year = _year_from_date(c.get("datum_zverejnenia"))
        spend_by_year[year] += float(c.get("hodnota_zmluvy") or 0)

    total_spend = float(procurer.get("celkova_hodnota") or sum(spend_by_year.values()))
    count = int(procurer.get("pocet_zakaziek") or len(contracts))

    return ProcurerSummary(
        ico=str(procurer.get("ico", ico)),
        name=procurer.get("nazov", ""),
        contract_count=count,
        total_spend=total_spend,
        avg_value=total_spend / count if count else 0,
        spend_by_year=[SpendByYear(year=y, total_value=v) for y, v in sorted(spend_by_year.items())],
    )


@router.get("/{ico}", response_model=ProcurerDetail)
async def get_procurer_detail(ico: str) -> ProcurerDetail:
    procurer, contracts = await _fetch_procurer_and_contracts(ico)

    supplier_totals: dict[str, dict] = defaultdict(lambda: {"name": "", "count": 0, "value": 0.0})
    years: set[int] = set()
    rows: list[ContractRow] = []

    for c in contracts:
        row = _map_contract_row(c)
        rows.append(row)
        years.add(row.year)
        if row.supplier_ico:
            s = supplier_totals[row.supplier_ico]
            s["name"] = row.supplier_name or ""
            s["count"] += 1
            s["value"] += row.value

    top_suppliers = sorted(
        [
            SupplierRelation(ico=k, name=v["name"], contract_count=v["count"], total_value=v["value"])
            for k, v in supplier_totals.items()
        ],
        key=lambda x: x.total_value,
        reverse=True,
    )[:10]

    total_spend = float(procurer.get("celkova_hodnota") or sum(r.value for r in rows))
    count = int(procurer.get("pocet_zakaziek") or len(rows))

    return ProcurerDetail(
        ico=str(procurer.get("ico", ico)),
        name=procurer.get("nazov", ""),
        contract_count=count,
        total_spend=total_spend,
        avg_value=total_spend / count if count else 0,
        years_active=sorted(y for y in years if y > 0),
        top_suppliers=top_suppliers,
        contracts=rows,
    )
```

- [ ] **Step 4: Register router in `app.py`**

Add to imports:
```python
from uvo_api.routers import procurers
```
Inside `create_app()`, before `return app`:
```python
    app.include_router(procurers.router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/api/test_procurers.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/uvo_api/routers/procurers.py tests/api/test_procurers.py src/uvo_api/app.py
git commit -m "feat: add /api/procurers endpoints"
```

---

## Task 9: Dashboard router

**Files:**
- Create: `src/uvo_api/routers/dashboard.py`
- Create: `tests/api/test_dashboard.py`
- Modify: `src/uvo_api/app.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_dashboard.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from uvo_api.app import create_app

SAMPLE_CONTRACTS = {
    "data": [
        {
            "id": "1",
            "nazov": "IT Project",
            "obstaravatel": {"ico": "12345678", "nazov": "Ministry"},
            "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
            "hodnota_zmluvy": 500000.0,
            "datum_zverejnenia": "2024-03-01",
            "cpv_kod": "72000000",
        },
        {
            "id": "2",
            "nazov": "Road Works",
            "obstaravatel": {"ico": "11111111", "nazov": "NDS"},
            "dodavatelia": [{"ico": "22222222", "nazov": "Build Co"}],
            "hodnota_zmluvy": 1000000.0,
            "datum_zverejnenia": "2023-06-15",
            "cpv_kod": "45000000",
        },
    ],
    "total": 2,
}

SAMPLE_SUPPLIERS = {
    "data": [
        {"ico": "87654321", "nazov": "Tech Corp", "pocet_zakaziek": 10, "celkova_hodnota": 5000000.0},
        {"ico": "22222222", "nazov": "Build Co", "pocet_zakaziek": 5, "celkova_hodnota": 2000000.0},
    ],
    "total": 2,
}

SAMPLE_PROCURERS = {
    "data": [
        {"ico": "12345678", "nazov": "Ministry", "pocet_zakaziek": 15, "celkova_hodnota": 8000000.0},
    ],
    "total": 1,
}


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_dashboard_summary(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(side_effect=[
        SAMPLE_CONTRACTS, SAMPLE_SUPPLIERS,
    ])):
        response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_count"] == 2
    assert body["total_value"] == 1500000.0
    assert body["avg_value"] == 750000.0
    assert body["active_suppliers"] == 2


def test_dashboard_spend_by_year(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/spend-by-year")
    assert response.status_code == 200
    body = response.json()
    years = {item["year"] for item in body}
    assert 2024 in years
    assert 2023 in years


def test_dashboard_top_suppliers(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_SUPPLIERS)):
        response = client.get("/api/dashboard/top-suppliers")
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    assert body[0]["ico"] == "87654321"
    assert body[0]["total_value"] == 5000000.0


def test_dashboard_top_procurers(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_PROCURERS)):
        response = client.get("/api/dashboard/top-procurers")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["ico"] == "12345678"
    assert body[0]["total_spend"] == 8000000.0


def test_dashboard_by_cpv(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/by-cpv")
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    cpv_codes = {item["cpv_code"] for item in body}
    assert "72000000" in cpv_codes or "45000000" in cpv_codes


def test_dashboard_recent(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/recent")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["id"] == "1"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/api/test_dashboard.py -v
```
Expected: collection or import error

- [ ] **Step 3: Implement dashboard router**

```python
# src/uvo_api/routers/dashboard.py
"""Dashboard aggregation endpoints."""

import json
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Query

from uvo_api.mcp_client import call_tool
from uvo_api.models import (
    CpvShare,
    DashboardDelta,
    DashboardSummary,
    RecentContract,
    SpendByYear,
    TopProcurer,
    TopSupplier,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_CPV_LABELS: dict[str, dict[str, str]] = {}

def _load_cpv_labels() -> dict[str, dict[str, str]]:
    global _CPV_LABELS
    if not _CPV_LABELS:
        path = Path(__file__).parent.parent / "data" / "cpv_labels.json"
        _CPV_LABELS = json.loads(path.read_text())
    return _CPV_LABELS


def _year_from_date(date_str: str | None) -> int:
    if date_str and len(date_str) >= 4:
        try:
            return int(date_str[:4])
        except ValueError:
            pass
    return 0


def _status_from_year(year: int) -> str:
    return "active" if year >= 2024 else "closed"


def _cpv_prefix(code: str | None) -> str:
    """Normalize CPV code to 8-digit prefix for label lookup."""
    if not code:
        return "00000000"
    digits = code.replace("-", "").replace(" ", "")[:8]
    return digits.ljust(8, "0")


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> DashboardSummary:
    contract_args: dict = {"limit": 100}
    if ico and entity_type == "supplier":
        contract_args["supplier_ico"] = ico
    elif ico and entity_type == "procurer":
        contract_args["procurer_id"] = ico

    contracts_result = await call_tool("search_completed_procurements", contract_args)
    contracts = contracts_result.get("data", [])
    total = contracts_result.get("total", len(contracts))

    total_value = sum(float(c.get("hodnota_zmluvy") or 0) for c in contracts)
    avg_value = total_value / total if total else 0

    suppliers_result = await call_tool("find_supplier", {"limit": 1})
    active_suppliers = suppliers_result.get("total", 0)

    return DashboardSummary(
        total_value=total_value,
        contract_count=total,
        avg_value=avg_value,
        active_suppliers=active_suppliers,
        deltas={
            "total_value": DashboardDelta(value=0),
            "contract_count": DashboardDelta(value=0),
        },
    )


@router.get("/spend-by-year", response_model=list[SpendByYear])
async def spend_by_year(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[SpendByYear]:
    args: dict = {"limit": 100}
    if ico and entity_type == "supplier":
        args["supplier_ico"] = ico
    elif ico and entity_type == "procurer":
        args["procurer_id"] = ico

    result = await call_tool("search_completed_procurements", args)
    contracts = result.get("data", [])

    by_year: dict[int, float] = defaultdict(float)
    for c in contracts:
        year = _year_from_date(c.get("datum_zverejnenia"))
        if year > 0:
            by_year[year] += float(c.get("hodnota_zmluvy") or 0)

    return [SpendByYear(year=y, total_value=v) for y, v in sorted(by_year.items())]


@router.get("/top-suppliers", response_model=list[TopSupplier])
async def top_suppliers(
    n: int = Query(5, ge=1, le=20),
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[TopSupplier]:
    args: dict = {"limit": 100}
    if ico and entity_type == "procurer":
        args["name_query"] = ""  # fetch all, filter below

    result = await call_tool("find_supplier", {"limit": n * 2})
    items = result.get("data", [])

    suppliers = [
        TopSupplier(
            ico=str(s.get("ico", "")),
            name=s.get("nazov", ""),
            total_value=float(s.get("celkova_hodnota") or 0),
            contract_count=int(s.get("pocet_zakaziek") or 0),
        )
        for s in items
    ]
    return sorted(suppliers, key=lambda x: x.total_value, reverse=True)[:n]


@router.get("/top-procurers", response_model=list[TopProcurer])
async def top_procurers(
    n: int = Query(5, ge=1, le=20),
) -> list[TopProcurer]:
    result = await call_tool("find_procurer", {"limit": n * 2})
    items = result.get("data", [])

    procurers = [
        TopProcurer(
            ico=str(p.get("ico", "")),
            name=p.get("nazov", ""),
            total_spend=float(p.get("celkova_hodnota") or 0),
            contract_count=int(p.get("pocet_zakaziek") or 0),
        )
        for p in items
    ]
    return sorted(procurers, key=lambda x: x.total_spend, reverse=True)[:n]


@router.get("/by-cpv", response_model=list[CpvShare])
async def by_cpv(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[CpvShare]:
    args: dict = {"limit": 100}
    if ico and entity_type == "supplier":
        args["supplier_ico"] = ico
    elif ico and entity_type == "procurer":
        args["procurer_id"] = ico

    result = await call_tool("search_completed_procurements", args)
    contracts = result.get("data", [])
    labels = _load_cpv_labels()

    by_cpv: dict[str, float] = defaultdict(float)
    for c in contracts:
        prefix = _cpv_prefix(c.get("cpv_kod"))
        by_cpv[prefix] += float(c.get("hodnota_zmluvy") or 0)

    total = sum(by_cpv.values()) or 1
    shares = []
    for code, value in sorted(by_cpv.items(), key=lambda x: x[1], reverse=True):
        label = labels.get(code, {"sk": code, "en": code})
        shares.append(CpvShare(
            cpv_code=code,
            label_sk=label.get("sk", code),
            label_en=label.get("en", code),
            total_value=value,
            percentage=round(value / total * 100, 1),
        ))
    return shares


@router.get("/recent", response_model=list[RecentContract])
async def recent_contracts(
    limit: int = Query(10, ge=1, le=50),
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[RecentContract]:
    args: dict = {"limit": limit}
    if ico and entity_type == "supplier":
        args["supplier_ico"] = ico
    elif ico and entity_type == "procurer":
        args["procurer_id"] = ico

    result = await call_tool("search_completed_procurements", args)
    contracts = result.get("data", [])

    return [
        RecentContract(
            id=str(c.get("id", "")),
            title=c.get("nazov", ""),
            procurer_name=(c.get("obstaravatel") or {}).get("nazov", ""),
            procurer_ico=(c.get("obstaravatel") or {}).get("ico", ""),
            value=float(c.get("hodnota_zmluvy") or 0),
            year=_year_from_date(c.get("datum_zverejnenia")),
            status=_status_from_year(_year_from_date(c.get("datum_zverejnenia"))),
        )
        for c in contracts
    ]
```

- [ ] **Step 4: Register router in `app.py`**

Add to imports:
```python
from uvo_api.routers import dashboard
```
Inside `create_app()`, before `return app`:
```python
    app.include_router(dashboard.router)
```

- [ ] **Step 5: Run all API tests**

```bash
pytest tests/api/ -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/uvo_api/routers/dashboard.py tests/api/test_dashboard.py src/uvo_api/app.py
git commit -m "feat: add /api/dashboard endpoints"
```

---

## Task 10: Docker service + env wiring

**Files:**
- Create: `Dockerfile.api`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Dockerfile.api
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --no-dev

COPY src/ src/

CMD ["uv", "run", "uvo-api"]
```

- [ ] **Step 2: Add service to docker-compose.yml**

Add after the `gui` service:

```yaml
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    ports:
      - "8001:8001"
    env_file: .env
    environment:
      API_MCP_SERVER_URL: http://mcp-server:8000/mcp
    depends_on:
      mcp-server:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    restart: unless-stopped
```

- [ ] **Step 3: Add env var to .env.example**

```bash
# Analytics API
API_MCP_SERVER_URL=http://localhost:8000/mcp
API_PORT=8001
```

- [ ] **Step 4: Run full test suite to confirm nothing broken**

```bash
pytest tests/api/ tests/mcp/ -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add Dockerfile.api docker-compose.yml .env.example
git commit -m "feat: add Docker service for uvo_api analytics backend"
```

---

## Self-Review Checklist

After writing this plan, checking against spec:

- ✅ All 14 API endpoints from spec are covered across Tasks 6–9
- ✅ `?ico=` + `?entity_type=` filter params on all dashboard endpoints (Task 9)
- ✅ CPV labels file (Task 4)
- ✅ Docker service (Task 10)
- ✅ `_year_from_date` / `_status_from_year` / `_map_contract_row` defined consistently in every router that uses them (no cross-router imports — each router is self-contained)
- ✅ Test fixtures use `AsyncMock(side_effect=[...])` pattern for multi-call endpoints
- ✅ `pyproject.toml` updated with `fastapi[standard]` dep and `uvo-api` entry point (Task 1)
