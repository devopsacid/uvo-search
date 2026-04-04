# UVO Search Phase 1 (MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Working MCP server with 4 core procurement/entity tools + basic NiceGUI search page with server-side pagination, all test-covered.

**Architecture:** Two-process Python app -- MCP server (FastMCP, streamable-http on port 8000) wrapping UVOstat.sk API, and NiceGUI frontend (port 8080) calling MCP server as client. Both async throughout using httpx.

**Tech Stack:** Python 3.12+, uv, mcp[cli] SDK (FastMCP), NiceGUI 3.9+, httpx, Pydantic 2.x, pydantic-settings, cachetools, pytest + pytest-asyncio

---

## File Map

Every file created during Phase 1, with its responsibility:

```
uvo-search/
    pyproject.toml                          # Project metadata, dependencies, scripts
    .env.example                            # Template for required/optional env vars
    .gitignore                              # Python, .env, .nicegui/, __pycache__
    src/
        uvo_mcp/
            __init__.py                     # Package marker (empty)
            __main__.py                     # Entry point: python -m uvo_mcp (stdio or streamable-http)
            config.py                       # pydantic-settings Settings class
            models.py                       # Pydantic models: Procurement, Subject, PaginatedResponse, etc.
            server.py                       # FastMCP instance, AppContext dataclass, lifespan, health check
            tools/
                __init__.py                 # Package marker (empty)
                procurements.py             # search_completed_procurements, get_procurement_detail
                subjects.py                 # find_procurer, find_supplier
        uvo_gui/
            __init__.py                     # Package marker (empty)
            __main__.py                     # Entry point: python -m uvo_gui
            app.py                          # NiceGUI app setup, page imports, ui.run()
            config.py                       # GUI-specific settings (mcp_server_url, storage_secret, etc.)
            mcp_client.py                   # MCP client wrapper: call_tool(name, args) -> dict
            pages/
                __init__.py                 # Package marker (empty)
                search.py                   # / -- Main search page with SearchState, results table, pagination
            components/
                __init__.py                 # Package marker (empty)
                nav_header.py               # Shared navigation header with links
                detail_dialog.py            # Procurement detail dialog (row-click popup)
    tests/
        __init__.py                         # Package marker (empty)
        conftest.py                         # Shared fixtures: MockResponse, mock_http_client, mock_context
        mcp/
            __init__.py                     # Package marker (empty)
            test_config.py                  # Settings loading from env vars
            test_models.py                  # Pydantic model creation and serialization
            test_tools_procurements.py      # search_completed_procurements, get_procurement_detail
            test_tools_subjects.py          # find_procurer, find_supplier
        gui/
            __init__.py                     # Package marker (empty)
            test_gui_config.py              # GUI settings loading
            test_mcp_client.py              # MCP client wrapper tests
```

---

## Task 1: Project Scaffolding

### Step 1.1 -- Create pyproject.toml

- [ ] Create file `pyproject.toml` in project root:

```python
# File: pyproject.toml
```

```toml
[project]
name = "uvo-search"
version = "0.1.0"
description = "Search and browse Slovak government procurement data via MCP server and NiceGUI frontend"
requires-python = ">=3.12"
dependencies = [
    "mcp[cli]>=1.0.0",
    "nicegui>=3.9.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "cachetools>=5.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "respx>=0.22",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/uvo_mcp", "src/uvo_gui"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: marks tests that call real external APIs (deselect with '-m \"not integration\"')",
]

[project.scripts]
uvo-mcp = "uvo_mcp.__main__:main"
uvo-gui = "uvo_gui.__main__:main"
```

### Step 1.2 -- Create project directory structure

- [ ] Create all directories:

```bash
mkdir -p src/uvo_mcp/tools
mkdir -p src/uvo_gui/pages
mkdir -p src/uvo_gui/components
mkdir -p tests/mcp
mkdir -p tests/gui
```

### Step 1.3 -- Create all __init__.py files

- [ ] Create empty `__init__.py` files:

```bash
touch src/uvo_mcp/__init__.py
touch src/uvo_mcp/tools/__init__.py
touch src/uvo_gui/__init__.py
touch src/uvo_gui/pages/__init__.py
touch src/uvo_gui/components/__init__.py
touch tests/__init__.py
touch tests/mcp/__init__.py
touch tests/gui/__init__.py
```

### Step 1.4 -- Create .env.example

- [ ] Create file `.env.example`:

```bash
# Required
UVOSTAT_API_TOKEN=your-token-here
STORAGE_SECRET=change-this-to-a-random-string

# Optional -- data sources
UVOSTAT_BASE_URL=https://www.uvostat.sk
EKOSYSTEM_BASE_URL=https://datahub.ekosystem.slovensko.digital
EKOSYSTEM_API_TOKEN=

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

### Step 1.5 -- Create .gitignore

- [ ] Create file `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
*.egg

# Environment
.env
.venv/

# NiceGUI
.nicegui/

# IDE
.idea/
.vscode/
*.swp

# Testing
.pytest_cache/
htmlcov/
.coverage

# uv
.python-version
```

### Step 1.6 -- Install dependencies with uv

- [ ] Run:

```bash
uv sync --all-extras
```

Expected: dependencies install successfully, `uv.lock` is created.

### Step 1.7 -- Commit scaffolding

- [ ] Run:

```bash
git add pyproject.toml uv.lock .env.example .gitignore src/ tests/
git commit -m "chore: scaffold project structure with dependencies and empty packages"
```

---

## Task 2: MCP Server Config (TDD)

### Step 2.1 -- Write the failing test for Settings

- [ ] Create file `tests/mcp/test_config.py`:

```python
"""Tests for MCP server configuration via pydantic-settings."""

import os
import pytest
from unittest.mock import patch


class TestSettings:
    """Test that Settings loads from environment variables."""

    def test_settings_loads_required_token(self):
        """Settings should load UVOSTAT_API_TOKEN from env."""
        env = {
            "UVOSTAT_API_TOKEN": "test-token-abc123",
            "STORAGE_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            from uvo_mcp.config import Settings

            s = Settings()
            assert s.uvostat_api_token == "test-token-abc123"

    def test_settings_default_values(self):
        """Settings should have sensible defaults for optional fields."""
        env = {
            "UVOSTAT_API_TOKEN": "test-token",
            "STORAGE_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            from uvo_mcp.config import Settings

            s = Settings()
            assert s.uvostat_base_url == "https://www.uvostat.sk"
            assert s.cache_ttl_search == 300
            assert s.cache_ttl_entity == 3600
            assert s.cache_ttl_detail == 1800
            assert s.request_timeout == 30.0
            assert s.max_page_size == 100

    def test_settings_override_from_env(self):
        """Settings should pick up overridden values from environment."""
        env = {
            "UVOSTAT_API_TOKEN": "test-token",
            "STORAGE_SECRET": "test-secret",
            "CACHE_TTL_SEARCH": "600",
            "REQUEST_TIMEOUT": "15.0",
            "MAX_PAGE_SIZE": "50",
        }
        with patch.dict(os.environ, env, clear=False):
            from uvo_mcp.config import Settings

            s = Settings()
            assert s.cache_ttl_search == 600
            assert s.request_timeout == 15.0
            assert s.max_page_size == 50

    def test_settings_missing_required_token_raises(self):
        """Settings should raise ValidationError when UVOSTAT_API_TOKEN is missing."""
        from pydantic import ValidationError
        from uvo_mcp.config import Settings

        # Remove the token if it exists, keep other env vars
        env_without_token = {k: v for k, v in os.environ.items() if k != "UVOSTAT_API_TOKEN"}
        with patch.dict(os.environ, env_without_token, clear=True):
            with pytest.raises(ValidationError):
                Settings()
```

### Step 2.2 -- Run the test to confirm it fails

- [ ] Run:

```bash
uv run pytest tests/mcp/test_config.py -v
```

Expected output: `ModuleNotFoundError: No module named 'uvo_mcp.config'` (or `ImportError`).

### Step 2.3 -- Implement config.py

- [ ] Create file `src/uvo_mcp/config.py`:

```python
"""MCP server configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration for the UVO MCP server.

    All fields map to environment variables of the same name (uppercase).
    Required fields have no default and will raise ValidationError if missing.
    """

    uvostat_api_token: str
    uvostat_base_url: str = "https://www.uvostat.sk"
    ekosystem_base_url: str = "https://datahub.ekosystem.slovensko.digital"
    ekosystem_api_token: str = ""
    ted_base_url: str = "https://api.ted.europa.eu"
    cache_ttl_search: int = 300
    cache_ttl_entity: int = 3600
    cache_ttl_detail: int = 1800
    request_timeout: float = 30.0
    max_page_size: int = 100

    model_config = {"env_file": ".env", "env_prefix": ""}
```

### Step 2.4 -- Run the tests to confirm they pass

- [ ] Run:

```bash
uv run pytest tests/mcp/test_config.py -v
```

Expected output: all 4 tests pass (`4 passed`).

### Step 2.5 -- Commit

- [ ] Run:

```bash
git add src/uvo_mcp/config.py tests/mcp/test_config.py
git commit -m "feat: add MCP server Settings with pydantic-settings and full test coverage"
```

---

## Task 3: Pydantic Models (TDD)

### Step 3.1 -- Write the failing test for models

- [ ] Create file `tests/mcp/test_models.py`:

```python
"""Tests for Pydantic data models."""

from datetime import date


class TestPaginationSummary:
    def test_create_pagination_summary(self):
        from uvo_mcp.models import PaginationSummary

        summary = PaginationSummary(total_records=100, offset=0, limit=20)
        assert summary.total_records == 100
        assert summary.offset == 0
        assert summary.limit == 20

    def test_pagination_summary_serialization(self):
        from uvo_mcp.models import PaginationSummary

        summary = PaginationSummary(total_records=50, offset=20, limit=20)
        data = summary.model_dump()
        assert data == {"total_records": 50, "offset": 20, "limit": 20}


class TestPaginatedResponse:
    def test_create_paginated_response_with_procurement(self):
        from uvo_mcp.models import PaginatedResponse, PaginationSummary, Procurement

        response = PaginatedResponse[Procurement](
            summary=PaginationSummary(total_records=1, offset=0, limit=20),
            data=[
                Procurement(id="123", nazov="Test procurement"),
            ],
        )
        assert response.summary.total_records == 1
        assert len(response.data) == 1
        assert response.data[0].nazov == "Test procurement"

    def test_paginated_response_serialization(self):
        from uvo_mcp.models import PaginatedResponse, PaginationSummary, Subject

        response = PaginatedResponse[Subject](
            summary=PaginationSummary(total_records=2, offset=0, limit=20),
            data=[
                Subject(id="1", nazov="Entity A"),
                Subject(id="2", nazov="Entity B"),
            ],
        )
        data = response.model_dump()
        assert data["summary"]["total_records"] == 2
        assert len(data["data"]) == 2
        assert data["data"][0]["nazov"] == "Entity A"

    def test_paginated_response_empty(self):
        from uvo_mcp.models import PaginatedResponse, PaginationSummary, Procurement

        response = PaginatedResponse[Procurement](
            summary=PaginationSummary(total_records=0, offset=0, limit=20),
            data=[],
        )
        assert response.summary.total_records == 0
        assert response.data == []


class TestProcurement:
    def test_create_procurement_minimal(self):
        from uvo_mcp.models import Procurement

        p = Procurement(id="456", nazov="Dodavka IT vybavenia")
        assert p.id == "456"
        assert p.nazov == "Dodavka IT vybavenia"
        assert p.popis is None
        assert p.obstaravatel_id is None
        assert p.konecna_hodnota is None
        assert p.mena == "EUR"
        assert p.cpv_kody == []
        assert p.dodavatelia == []

    def test_create_procurement_full(self):
        from uvo_mcp.models import Procurement, SupplierSummary

        p = Procurement(
            id="789",
            nazov="Rekonstrukcia budovy",
            popis="Kompletna rekonstrukcia administrativnej budovy",
            obstaravatel_id="100",
            obstaravatel_nazov="Ministerstvo vnutra SR",
            obstaravatel_ico="00151866",
            predpokladana_hodnota=50000.0,
            konecna_hodnota=45230.0,
            mena="EUR",
            datum_vyhlasenia=date(2026, 1, 15),
            datum_zverejnenia=date(2026, 3, 15),
            datum_ukoncenia=date(2026, 3, 20),
            cpv_kod="72000000-5",
            cpv_kody=["72000000-5", "72200000-7"],
            stav="ukoncene",
            typ_postupu="Verejna sutaz",
            vestnik_cislo="123/2026",
            oznamenie_cislo="4521",
            dodavatelia=[
                SupplierSummary(
                    id="200", nazov="IT Solutions s.r.o.",
                    ico="12345678", hodnota=45230.0,
                ),
            ],
        )
        assert p.konecna_hodnota == 45230.0
        assert p.datum_zverejnenia == date(2026, 3, 15)
        assert len(p.dodavatelia) == 1
        assert p.dodavatelia[0].nazov == "IT Solutions s.r.o."

    def test_procurement_serialization_roundtrip(self):
        from uvo_mcp.models import Procurement

        p = Procurement(
            id="1",
            nazov="Test",
            datum_zverejnenia=date(2026, 1, 1),
            cpv_kody=["72000000-5"],
        )
        data = p.model_dump(mode="json")
        assert data["datum_zverejnenia"] == "2026-01-01"
        assert data["cpv_kody"] == ["72000000-5"]

        # Roundtrip
        p2 = Procurement.model_validate(data)
        assert p2.id == "1"
        assert p2.datum_zverejnenia == date(2026, 1, 1)


class TestSupplierSummary:
    def test_create_supplier_summary(self):
        from uvo_mcp.models import SupplierSummary

        s = SupplierSummary(nazov="ACME Corp")
        assert s.nazov == "ACME Corp"
        assert s.id is None
        assert s.ico is None
        assert s.hodnota is None

    def test_supplier_summary_full(self):
        from uvo_mcp.models import SupplierSummary

        s = SupplierSummary(
            id="55", nazov="Test s.r.o.", ico="87654321", hodnota=10000.0
        )
        data = s.model_dump()
        assert data["ico"] == "87654321"
        assert data["hodnota"] == 10000.0


class TestSubject:
    def test_create_subject_minimal(self):
        from uvo_mcp.models import Subject

        s = Subject(id="1", nazov="Mesto Bratislava")
        assert s.id == "1"
        assert s.nazov == "Mesto Bratislava"
        assert s.ico is None
        assert s.pocet_obstaravani is None

    def test_create_subject_full(self):
        from uvo_mcp.models import Subject

        s = Subject(
            id="42",
            nazov="Ministerstvo vnutra SR",
            ico="00151866",
            dic="2020571520",
            adresa="Pribinova 2, Bratislava",
            typ="obstaravatel",
            pravna_forma="Rozpoctova organizacia",
            krajina="SK",
            pocet_obstaravani=342,
            celkova_hodnota=15000000.0,
        )
        assert s.pocet_obstaravani == 342
        assert s.celkova_hodnota == 15000000.0

    def test_subject_serialization(self):
        from uvo_mcp.models import Subject

        s = Subject(id="1", nazov="Test", ico="12345678")
        data = s.model_dump()
        assert data["ico"] == "12345678"
        assert data["typ"] is None
```

### Step 3.2 -- Run the test to confirm it fails

- [ ] Run:

```bash
uv run pytest tests/mcp/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'uvo_mcp.models'`.

### Step 3.3 -- Implement models.py

- [ ] Create file `src/uvo_mcp/models.py`:

```python
"""Pydantic data models for UVO procurement data."""

from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationSummary(BaseModel):
    """Metadata about a paginated API response."""

    total_records: int = Field(description="Total matching records across all pages")
    offset: int = Field(description="Current offset")
    limit: int = Field(description="Page size")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapping a list of results."""

    summary: PaginationSummary
    data: list[T]


class SupplierSummary(BaseModel):
    """Brief supplier info embedded in a procurement record."""

    id: str | None = Field(default=None, description="Internal supplier ID")
    nazov: str = Field(description="Supplier name")
    ico: str | None = Field(default=None, description="ICO (8-digit company ID)")
    hodnota: float | None = Field(
        default=None, description="Contract value for this supplier"
    )


class Procurement(BaseModel):
    """A single procurement record (completed or announced)."""

    id: str = Field(description="Internal procurement ID")
    nazov: str = Field(description="Procurement title")
    popis: str | None = Field(default=None, description="Description text")
    obstaravatel_id: str | None = Field(
        default=None, description="Contracting authority ID"
    )
    obstaravatel_nazov: str | None = Field(
        default=None, description="Contracting authority name"
    )
    obstaravatel_ico: str | None = Field(
        default=None, description="Contracting authority ICO"
    )
    predpokladana_hodnota: float | None = Field(
        default=None, description="Estimated value in EUR"
    )
    konecna_hodnota: float | None = Field(
        default=None, description="Final awarded value in EUR"
    )
    mena: str = Field(default="EUR", description="Currency code")
    datum_vyhlasenia: date | None = Field(
        default=None, description="Announcement date"
    )
    datum_zverejnenia: date | None = Field(
        default=None, description="Publication date"
    )
    datum_ukoncenia: date | None = Field(default=None, description="Closing date")
    cpv_kod: str | None = Field(default=None, description="Primary CPV code")
    cpv_kody: list[str] = Field(default_factory=list, description="All CPV codes")
    stav: str | None = Field(
        default=None, description="Status: vyhlasene, ukoncene, zrusene"
    )
    typ_postupu: str | None = Field(default=None, description="Procedure type")
    vestnik_cislo: str | None = Field(
        default=None, description="Bulletin issue number"
    )
    oznamenie_cislo: str | None = Field(default=None, description="Notice number")
    dodavatelia: list[SupplierSummary] = Field(
        default_factory=list, description="Winning suppliers"
    )


class Subject(BaseModel):
    """A contracting authority or supplier entity."""

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
```

### Step 3.4 -- Run the tests to confirm they pass

- [ ] Run:

```bash
uv run pytest tests/mcp/test_models.py -v
```

Expected: all 12 tests pass (`12 passed`).

### Step 3.5 -- Commit

- [ ] Run:

```bash
git add src/uvo_mcp/models.py tests/mcp/test_models.py
git commit -m "feat: add Pydantic data models for procurement, subject, and pagination"
```

---

## Task 4: MCP Server Core

### Step 4.1 -- Create server.py with FastMCP, AppContext, and lifespan

- [ ] Create file `src/uvo_mcp/server.py`:

```python
"""FastMCP server definition with shared httpx client lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import FastMCP

from uvo_mcp.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Shared application context available to all MCP tools via lifespan."""

    http_client: httpx.AsyncClient
    settings: Settings


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Create a shared httpx client for the lifetime of the MCP server."""
    settings = Settings()
    async with httpx.AsyncClient(
        base_url=settings.uvostat_base_url,
        headers={"ApiToken": settings.uvostat_api_token},
        timeout=settings.request_timeout,
    ) as client:
        logger.info("MCP server starting, httpx client ready")
        yield AppContext(http_client=client, settings=settings)
        logger.info("MCP server shutting down")


mcp = FastMCP(
    "UVO Search",
    description="Search Slovak government procurement data from UVOstat.sk and related sources",
    lifespan=app_lifespan,
    json_response=True,
)
```

### Step 4.2 -- Create __main__.py entry point

- [ ] Create file `src/uvo_mcp/__main__.py`:

```python
"""Entry point for the UVO MCP server.

Usage:
    python -m uvo_mcp                  # streamable-http on port 8000 (default)
    python -m uvo_mcp stdio            # stdio transport for Claude Desktop/Code
"""

import sys


def main():
    from uvo_mcp.server import mcp

    transport = sys.argv[1] if len(sys.argv) > 1 else "streamable-http"
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
```

### Step 4.3 -- Test that server can be imported without errors

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token uv run python -c "from uvo_mcp.server import mcp, AppContext; print('OK: server imports cleanly')"
```

Expected output: `OK: server imports cleanly`

### Step 4.4 -- Commit

- [ ] Run:

```bash
git add src/uvo_mcp/server.py src/uvo_mcp/__main__.py
git commit -m "feat: add MCP server core with FastMCP, AppContext lifespan, and entry point"
```

---

## Task 5: search_completed_procurements Tool (TDD)

### Step 5.1 -- Create shared test fixtures in conftest.py

- [ ] Create file `tests/conftest.py`:

```python
"""Shared test fixtures for UVO Search tests."""

import httpx
import pytest
import respx


class MockResponse:
    """Simple mock for httpx.Response used in manual mocking scenarios."""

    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data
        self.text = str(json_data)

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://test.example.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=request,
                response=response,
            )


@pytest.fixture
def mock_http_client():
    """Create a mocked httpx.AsyncClient using respx."""
    with respx.mock(base_url="https://www.uvostat.sk") as mock:
        client = httpx.AsyncClient(
            base_url="https://www.uvostat.sk",
            headers={"ApiToken": "test-token"},
            timeout=30.0,
        )
        yield client, mock


@pytest.fixture
def mock_context(mock_http_client):
    """Create a mock MCP Context with AppContext containing mocked httpx client."""
    from unittest.mock import MagicMock

    from uvo_mcp.config import Settings
    from uvo_mcp.server import AppContext

    client, mock = mock_http_client
    settings = Settings(
        uvostat_api_token="test-token",
        uvostat_base_url="https://www.uvostat.sk",
    )
    app_ctx = AppContext(http_client=client, settings=settings)

    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_ctx

    return ctx, mock
```

### Step 5.2 -- Write the failing tests for search_completed_procurements

- [ ] Create file `tests/mcp/test_tools_procurements.py`:

```python
"""Tests for procurement MCP tools."""

import httpx
import pytest
import respx


class TestSearchCompletedProcurements:
    """Tests for the search_completed_procurements MCP tool."""

    @pytest.mark.asyncio
    async def test_basic_search_returns_paginated_response(self, mock_context):
        """Basic search with no filters returns a PaginatedResponse dict."""
        ctx, mock = mock_context

        mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 2, "offset": 0, "limit": 20},
                    "data": [
                        {"id": "101", "nazov": "Dodavka IT vybavenia"},
                        {"id": "102", "nazov": "Rekonstrukcia budovy"},
                    ],
                },
            )
        )

        from uvo_mcp.tools.procurements import search_completed_procurements

        result = await search_completed_procurements(
            ctx=ctx, limit=20, offset=0
        )

        assert result["summary"]["total_records"] == 2
        assert len(result["data"]) == 2
        assert result["data"][0]["id"] == "101"
        assert result["data"][0]["nazov"] == "Dodavka IT vybavenia"

    @pytest.mark.asyncio
    async def test_search_with_cpv_codes_passes_correct_params(self, mock_context):
        """CPV code filter should be passed as cpv[] query parameter."""
        ctx, mock = mock_context

        route = mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 5, "offset": 0, "limit": 20},
                    "data": [{"id": "201", "nazov": "IT zakazka"}],
                },
            )
        )

        from uvo_mcp.tools.procurements import search_completed_procurements

        result = await search_completed_procurements(
            ctx=ctx,
            cpv_codes=["72000000-5"],
            limit=20,
            offset=0,
        )

        assert result["summary"]["total_records"] == 5
        assert route.called
        request = route.calls[0].request
        # Check that cpv[] parameter was included in the URL
        assert "cpv%5B%5D=72000000-5" in str(request.url) or "cpv[]=72000000-5" in str(request.url)

    @pytest.mark.asyncio
    async def test_search_with_date_range_passes_correct_params(self, mock_context):
        """Date filters should be passed as datum_zverejnenia_od/do parameters."""
        ctx, mock = mock_context

        route = mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 3, "offset": 0, "limit": 20},
                    "data": [{"id": "301", "nazov": "Stavba"}],
                },
            )
        )

        from uvo_mcp.tools.procurements import search_completed_procurements

        result = await search_completed_procurements(
            ctx=ctx,
            date_from="2024-01-01",
            date_to="2024-12-31",
            limit=20,
            offset=0,
        )

        assert result["summary"]["total_records"] == 3
        request = route.calls[0].request
        url_str = str(request.url)
        assert "datum_zverejnenia_od=2024-01-01" in url_str
        assert "datum_zverejnenia_do=2024-12-31" in url_str

    @pytest.mark.asyncio
    async def test_search_with_text_query(self, mock_context):
        """Text query should be passed as 'text' parameter."""
        ctx, mock = mock_context

        route = mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 1, "offset": 0, "limit": 20},
                    "data": [{"id": "401", "nazov": "IT infrastruktura"}],
                },
            )
        )

        from uvo_mcp.tools.procurements import search_completed_procurements

        result = await search_completed_procurements(
            ctx=ctx,
            text_query="infrastruktura",
            limit=20,
            offset=0,
        )

        assert result["summary"]["total_records"] == 1
        request = route.calls[0].request
        assert "text=infrastruktura" in str(request.url)

    @pytest.mark.asyncio
    async def test_api_error_returns_structured_error_dict(self, mock_context):
        """API errors should return a dict with 'error' and 'status_code' keys."""
        ctx, mock = mock_context

        mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )

        from uvo_mcp.tools.procurements import search_completed_procurements

        result = await search_completed_procurements(
            ctx=ctx, limit=20, offset=0
        )

        assert "error" in result
        assert result["status_code"] == 500

    @pytest.mark.asyncio
    async def test_network_error_returns_structured_error_dict(self, mock_context):
        """Network errors (timeout, connection refused) should return an error dict."""
        ctx, mock = mock_context

        mock.get("/api/ukoncene_obstaravania").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        from uvo_mcp.tools.procurements import search_completed_procurements

        result = await search_completed_procurements(
            ctx=ctx, limit=20, offset=0
        )

        assert "error" in result
        assert "Connection" in result["error"] or "connection" in result["error"]
```

### Step 5.3 -- Run the tests to confirm they fail

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token uv run pytest tests/mcp/test_tools_procurements.py -v
```

Expected: `ModuleNotFoundError: No module named 'uvo_mcp.tools.procurements'`.

### Step 5.4 -- Implement the search_completed_procurements tool

- [ ] Create file `src/uvo_mcp/tools/procurements.py`:

```python
"""MCP tools for searching and retrieving procurement records."""

import logging

import httpx
from mcp.server.fastmcp import Context

from uvo_mcp.server import AppContext

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    """Extract AppContext from the MCP context."""
    return ctx.request_context.lifespan_context


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
    """Search completed (awarded) government procurements from the Slovak UVO registry.

    Returns finalized procurement records including contract values, winning suppliers,
    CPV codes, and publication dates. Use this for historical analysis of awarded contracts.

    Examples:
    - Find IT procurements since 2024: cpv_codes=["72000000-5"], date_from="2024-01-01"
    - Find procurements by a specific entity: procurer_id="86958"
    - Find contracts won by a company: supplier_ico="35763469"
    """
    app_ctx = _get_app_context(ctx)
    client = app_ctx.http_client

    params: dict = {
        "limit": min(limit, app_ctx.settings.max_page_size),
        "offset": max(offset, 0),
    }

    if text_query:
        params["text"] = text_query
    if cpv_codes:
        params["cpv[]"] = cpv_codes
    if procurer_id:
        params["obstaravatel_id"] = procurer_id
    if supplier_ico:
        params["dodavatel_ico"] = supplier_ico
    if date_from:
        params["datum_zverejnenia_od"] = date_from
    if date_to:
        params["datum_zverejnenia_do"] = date_to

    try:
        response = await client.get("/api/ukoncene_obstaravania", params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("API error searching procurements: %s", exc)
        return {
            "error": f"API returned HTTP {exc.response.status_code}",
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        logger.error("Network error searching procurements: %s", exc)
        return {
            "error": f"Connection error: {exc}",
            "status_code": 0,
        }
```

### Step 5.5 -- Register the tool on the MCP server

- [ ] Add the following to the bottom of `src/uvo_mcp/server.py`:

```python
# Register tool modules -- importing them registers their @mcp.tool() decorators
import uvo_mcp.tools.procurements  # noqa: F401, E402
```

Wait -- the tool is not yet decorated with `@mcp.tool()`. We need to update `tools/procurements.py` to import and use the `mcp` instance. However, this creates a circular import (server imports tools, tools import mcp from server). The standard FastMCP pattern is:

1. Define `mcp` in `server.py`
2. Tools import `mcp` from `server` and use `@mcp.tool()`
3. `server.py` imports tools at the bottom (after `mcp` is defined)

Update the tool registration. Add to the **top** of `src/uvo_mcp/tools/procurements.py`, after the existing imports:

```python
from uvo_mcp.server import mcp
```

And decorate the function:

```python
@mcp.tool()
async def search_completed_procurements(
```

The full updated `src/uvo_mcp/tools/procurements.py` is:

```python
"""MCP tools for searching and retrieving procurement records."""

import logging

import httpx
from mcp.server.fastmcp import Context

from uvo_mcp.server import AppContext, mcp

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    """Extract AppContext from the MCP context."""
    return ctx.request_context.lifespan_context


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
    """Search completed (awarded) government procurements from the Slovak UVO registry.

    Returns finalized procurement records including contract values, winning suppliers,
    CPV codes, and publication dates. Use this for historical analysis of awarded contracts.

    Examples:
    - Find IT procurements since 2024: cpv_codes=["72000000-5"], date_from="2024-01-01"
    - Find procurements by a specific entity: procurer_id="86958"
    - Find contracts won by a company: supplier_ico="35763469"
    """
    app_ctx = _get_app_context(ctx)
    client = app_ctx.http_client

    params: dict = {
        "limit": min(limit, app_ctx.settings.max_page_size),
        "offset": max(offset, 0),
    }

    if text_query:
        params["text"] = text_query
    if cpv_codes:
        params["cpv[]"] = cpv_codes
    if procurer_id:
        params["obstaravatel_id"] = procurer_id
    if supplier_ico:
        params["dodavatel_ico"] = supplier_ico
    if date_from:
        params["datum_zverejnenia_od"] = date_from
    if date_to:
        params["datum_zverejnenia_do"] = date_to

    try:
        response = await client.get("/api/ukoncene_obstaravania", params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("API error searching procurements: %s", exc)
        return {
            "error": f"API returned HTTP {exc.response.status_code}",
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        logger.error("Network error searching procurements: %s", exc)
        return {
            "error": f"Connection error: {exc}",
            "status_code": 0,
        }
```

And add to the bottom of `src/uvo_mcp/server.py`:

```python
# Import tool modules to register @mcp.tool() decorators
import uvo_mcp.tools.procurements  # noqa: F401, E402
```

### Step 5.6 -- Run the tests to confirm they pass

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token uv run pytest tests/mcp/test_tools_procurements.py -v
```

Expected: all 6 tests pass (`6 passed`).

### Step 5.7 -- Commit

- [ ] Run:

```bash
git add src/uvo_mcp/tools/procurements.py src/uvo_mcp/server.py tests/conftest.py tests/mcp/test_tools_procurements.py
git commit -m "feat: add search_completed_procurements MCP tool with full test coverage"
```

---

## Task 6: get_procurement_detail Tool (TDD)

### Step 6.1 -- Write the failing tests

- [ ] Add to `tests/mcp/test_tools_procurements.py`:

```python
class TestGetProcurementDetail:
    """Tests for the get_procurement_detail MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_procurement_with_suppliers(self, mock_context):
        """Fetching a procurement by ID returns full detail with dodavatelia."""
        ctx, mock = mock_context

        mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 1, "offset": 0, "limit": 1},
                    "data": [
                        {
                            "id": "999",
                            "nazov": "Dodavka IT vybavenia",
                            "obstaravatel_nazov": "Ministerstvo vnutra SR",
                            "konecna_hodnota": 45230.0,
                            "dodavatelia": [
                                {
                                    "id": "200",
                                    "nazov": "IT Solutions s.r.o.",
                                    "ico": "12345678",
                                    "hodnota": 45230.0,
                                },
                            ],
                        },
                    ],
                },
            )
        )

        from uvo_mcp.tools.procurements import get_procurement_detail

        result = await get_procurement_detail(ctx=ctx, procurement_id="999")

        assert result["id"] == "999"
        assert result["nazov"] == "Dodavka IT vybavenia"
        assert len(result["dodavatelia"]) == 1
        assert result["dodavatelia"][0]["nazov"] == "IT Solutions s.r.o."

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self, mock_context):
        """Requesting a nonexistent procurement ID returns an error dict."""
        ctx, mock = mock_context

        mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 0, "offset": 0, "limit": 1},
                    "data": [],
                },
            )
        )

        from uvo_mcp.tools.procurements import get_procurement_detail

        result = await get_procurement_detail(ctx=ctx, procurement_id="nonexistent")

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_api_error_returns_error_dict(self, mock_context):
        """API error on detail fetch returns structured error."""
        ctx, mock = mock_context

        mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(500, json={"error": "Server Error"})
        )

        from uvo_mcp.tools.procurements import get_procurement_detail

        result = await get_procurement_detail(ctx=ctx, procurement_id="999")

        assert "error" in result
        assert result["status_code"] == 500
```

### Step 6.2 -- Run the tests to confirm they fail

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token uv run pytest tests/mcp/test_tools_procurements.py::TestGetProcurementDetail -v
```

Expected: `ImportError` or `AttributeError` (function does not exist yet).

### Step 6.3 -- Implement get_procurement_detail

- [ ] Add to the bottom of `src/uvo_mcp/tools/procurements.py` (before any trailing comments):

```python
@mcp.tool()
async def get_procurement_detail(
    ctx: Context,
    procurement_id: str,
) -> dict:
    """Get full details of a specific procurement including all contracts and suppliers.

    Returns the complete procurement record with list of all participating suppliers,
    contract values, and procurement metadata.
    """
    app_ctx = _get_app_context(ctx)
    client = app_ctx.http_client

    params = {"id[]": procurement_id}

    try:
        response = await client.get("/api/ukoncene_obstaravania", params=params)
        response.raise_for_status()
        data = response.json()

        if not data.get("data"):
            return {"error": f"Procurement {procurement_id} not found", "status_code": 404}

        return data["data"][0]
    except httpx.HTTPStatusError as exc:
        logger.error("API error fetching procurement detail: %s", exc)
        return {
            "error": f"API returned HTTP {exc.response.status_code}",
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        logger.error("Network error fetching procurement detail: %s", exc)
        return {
            "error": f"Connection error: {exc}",
            "status_code": 0,
        }
```

### Step 6.4 -- Run the tests to confirm they pass

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token uv run pytest tests/mcp/test_tools_procurements.py -v
```

Expected: all 9 tests pass (`9 passed`).

### Step 6.5 -- Commit

- [ ] Run:

```bash
git add src/uvo_mcp/tools/procurements.py tests/mcp/test_tools_procurements.py
git commit -m "feat: add get_procurement_detail MCP tool with not-found and error handling"
```

---

## Task 7: find_procurer Tool (TDD)

### Step 7.1 -- Write the failing tests

- [ ] Create file `tests/mcp/test_tools_subjects.py`:

```python
"""Tests for subject (procurer/supplier) MCP tools."""

import httpx
import pytest
import respx


class TestFindProcurer:
    """Tests for the find_procurer MCP tool."""

    @pytest.mark.asyncio
    async def test_search_by_name_returns_results(self, mock_context):
        """Searching by name_query returns matching procurers."""
        ctx, mock = mock_context

        route = mock.get("/api/obstaravatelia").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 2, "offset": 0, "limit": 20},
                    "data": [
                        {"id": "1", "nazov": "Ministerstvo vnutra SR", "ico": "00151866"},
                        {"id": "2", "nazov": "Ministerstvo financii SR", "ico": "00151742"},
                    ],
                },
            )
        )

        from uvo_mcp.tools.subjects import find_procurer

        result = await find_procurer(ctx=ctx, name_query="Ministerstvo", limit=20, offset=0)

        assert result["summary"]["total_records"] == 2
        assert len(result["data"]) == 2
        assert result["data"][0]["nazov"] == "Ministerstvo vnutra SR"

        # Verify the name query parameter was sent
        request = route.calls[0].request
        assert "text=Ministerstvo" in str(request.url)

    @pytest.mark.asyncio
    async def test_search_by_ico_exact_match(self, mock_context):
        """Searching by ICO returns exact match."""
        ctx, mock = mock_context

        route = mock.get("/api/obstaravatelia").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 1, "offset": 0, "limit": 20},
                    "data": [
                        {"id": "1", "nazov": "Ministerstvo vnutra SR", "ico": "00151866"},
                    ],
                },
            )
        )

        from uvo_mcp.tools.subjects import find_procurer

        result = await find_procurer(ctx=ctx, ico="00151866", limit=20, offset=0)

        assert result["summary"]["total_records"] == 1
        request = route.calls[0].request
        assert "ico=00151866" in str(request.url)

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_context):
        """Searching with no matches returns empty data list."""
        ctx, mock = mock_context

        mock.get("/api/obstaravatelia").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 0, "offset": 0, "limit": 20},
                    "data": [],
                },
            )
        )

        from uvo_mcp.tools.subjects import find_procurer

        result = await find_procurer(
            ctx=ctx, name_query="NONEXISTENT_ENTITY", limit=20, offset=0
        )

        assert result["summary"]["total_records"] == 0
        assert result["data"] == []

    @pytest.mark.asyncio
    async def test_api_error_returns_error_dict(self, mock_context):
        """API error returns structured error dict."""
        ctx, mock = mock_context

        mock.get("/api/obstaravatelia").mock(
            return_value=httpx.Response(500, json={"error": "Server Error"})
        )

        from uvo_mcp.tools.subjects import find_procurer

        result = await find_procurer(ctx=ctx, name_query="test", limit=20, offset=0)

        assert "error" in result
        assert result["status_code"] == 500
```

### Step 7.2 -- Run the tests to confirm they fail

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token uv run pytest tests/mcp/test_tools_subjects.py::TestFindProcurer -v
```

Expected: `ModuleNotFoundError: No module named 'uvo_mcp.tools.subjects'`.

### Step 7.3 -- Implement find_procurer

- [ ] Create file `src/uvo_mcp/tools/subjects.py`:

```python
"""MCP tools for searching contracting authorities and suppliers."""

import logging

import httpx
from mcp.server.fastmcp import Context

from uvo_mcp.server import AppContext, mcp

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    """Extract AppContext from the MCP context."""
    return ctx.request_context.lifespan_context


@mcp.tool()
async def find_procurer(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Find contracting authorities (obstaravatelia) in the procurement registry.

    Use this to look up government bodies, municipalities, state enterprises, and other
    public entities that issue procurement contracts. Returns entity ID, name, ICO,
    address, and procurement statistics.

    Provide either name_query (partial match) or ico (exact match), or both.
    """
    app_ctx = _get_app_context(ctx)
    client = app_ctx.http_client

    params: dict = {
        "limit": min(limit, app_ctx.settings.max_page_size),
        "offset": max(offset, 0),
    }

    if name_query:
        params["text"] = name_query
    if ico:
        params["ico"] = ico

    try:
        response = await client.get("/api/obstaravatelia", params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("API error searching procurers: %s", exc)
        return {
            "error": f"API returned HTTP {exc.response.status_code}",
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        logger.error("Network error searching procurers: %s", exc)
        return {
            "error": f"Connection error: {exc}",
            "status_code": 0,
        }
```

### Step 7.4 -- Register the tool module in server.py

- [ ] Add to the bottom of `src/uvo_mcp/server.py` (alongside the procurements import):

```python
import uvo_mcp.tools.subjects  # noqa: F401, E402
```

### Step 7.5 -- Run the tests to confirm they pass

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token uv run pytest tests/mcp/test_tools_subjects.py::TestFindProcurer -v
```

Expected: all 4 tests pass (`4 passed`).

### Step 7.6 -- Commit

- [ ] Run:

```bash
git add src/uvo_mcp/tools/subjects.py src/uvo_mcp/server.py tests/mcp/test_tools_subjects.py
git commit -m "feat: add find_procurer MCP tool for searching contracting authorities"
```

---

## Task 8: find_supplier Tool (TDD)

### Step 8.1 -- Write the failing tests

- [ ] Add to `tests/mcp/test_tools_subjects.py`:

```python
class TestFindSupplier:
    """Tests for the find_supplier MCP tool."""

    @pytest.mark.asyncio
    async def test_search_by_name_returns_results(self, mock_context):
        """Searching by name_query returns matching suppliers."""
        ctx, mock = mock_context

        route = mock.get("/api/dodavatelia").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 1, "offset": 0, "limit": 20},
                    "data": [
                        {"id": "10", "nazov": "IT Solutions s.r.o.", "ico": "12345678"},
                    ],
                },
            )
        )

        from uvo_mcp.tools.subjects import find_supplier

        result = await find_supplier(ctx=ctx, name_query="IT Solutions", limit=20, offset=0)

        assert result["summary"]["total_records"] == 1
        assert result["data"][0]["nazov"] == "IT Solutions s.r.o."
        request = route.calls[0].request
        assert "text=IT" in str(request.url)

    @pytest.mark.asyncio
    async def test_search_by_ico(self, mock_context):
        """Searching by ICO returns exact match for supplier."""
        ctx, mock = mock_context

        route = mock.get("/api/dodavatelia").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 1, "offset": 0, "limit": 20},
                    "data": [
                        {"id": "10", "nazov": "IT Solutions s.r.o.", "ico": "12345678"},
                    ],
                },
            )
        )

        from uvo_mcp.tools.subjects import find_supplier

        result = await find_supplier(ctx=ctx, ico="12345678", limit=20, offset=0)

        assert result["summary"]["total_records"] == 1
        request = route.calls[0].request
        assert "ico=12345678" in str(request.url)

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_context):
        """No matches returns empty data list."""
        ctx, mock = mock_context

        mock.get("/api/dodavatelia").mock(
            return_value=httpx.Response(
                200,
                json={
                    "summary": {"total_records": 0, "offset": 0, "limit": 20},
                    "data": [],
                },
            )
        )

        from uvo_mcp.tools.subjects import find_supplier

        result = await find_supplier(
            ctx=ctx, name_query="NONEXISTENT", limit=20, offset=0
        )

        assert result["summary"]["total_records"] == 0
        assert result["data"] == []

    @pytest.mark.asyncio
    async def test_api_error_returns_error_dict(self, mock_context):
        """API error returns structured error dict."""
        ctx, mock = mock_context

        mock.get("/api/dodavatelia").mock(
            return_value=httpx.Response(503, json={"error": "Service Unavailable"})
        )

        from uvo_mcp.tools.subjects import find_supplier

        result = await find_supplier(ctx=ctx, name_query="test", limit=20, offset=0)

        assert "error" in result
        assert result["status_code"] == 503
```

### Step 8.2 -- Run the tests to confirm they fail

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token uv run pytest tests/mcp/test_tools_subjects.py::TestFindSupplier -v
```

Expected: `ImportError: cannot import name 'find_supplier' from 'uvo_mcp.tools.subjects'`.

### Step 8.3 -- Implement find_supplier

- [ ] Add to the bottom of `src/uvo_mcp/tools/subjects.py`:

```python
@mcp.tool()
async def find_supplier(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Find suppliers (dodavatelia) who have won government procurement contracts.

    Use this to look up companies that participate in public procurement. Returns
    entity ID, name, ICO, address, country, and contract history summary.

    Provide either name_query (partial match) or ico (exact match), or both.
    """
    app_ctx = _get_app_context(ctx)
    client = app_ctx.http_client

    params: dict = {
        "limit": min(limit, app_ctx.settings.max_page_size),
        "offset": max(offset, 0),
    }

    if name_query:
        params["text"] = name_query
    if ico:
        params["ico"] = ico

    try:
        response = await client.get("/api/dodavatelia", params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("API error searching suppliers: %s", exc)
        return {
            "error": f"API returned HTTP {exc.response.status_code}",
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        logger.error("Network error searching suppliers: %s", exc)
        return {
            "error": f"Connection error: {exc}",
            "status_code": 0,
        }
```

### Step 8.4 -- Run the tests to confirm they pass

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token uv run pytest tests/mcp/test_tools_subjects.py -v
```

Expected: all 8 tests pass (`8 passed`).

### Step 8.5 -- Commit

- [ ] Run:

```bash
git add src/uvo_mcp/tools/subjects.py tests/mcp/test_tools_subjects.py
git commit -m "feat: add find_supplier MCP tool for searching procurement suppliers"
```

---

## Task 9: MCP Server Health Check and Entry Point Verification

### Step 9.1 -- Add health check to server.py

- [ ] Add to `src/uvo_mcp/server.py`, after the `mcp` definition but before the tool imports:

```python
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


async def health_check(request):
    """Health check endpoint for container orchestration."""
    return JSONResponse({"status": "ok", "service": "uvo-mcp"})
```

Note: The FastMCP server uses Starlette under the hood. We will add the health route when the server starts. However, since FastMCP manages its own ASGI app, the simplest approach for Phase 1 is to add a custom route via the underlying app. Let us take a simpler approach -- add a health check as an MCP tool that can also be called via HTTP.

Actually, for Phase 1, let us keep it simple. The MCP server's `/mcp` endpoint being reachable is sufficient for health checking. We will add a dedicated `/health` endpoint by hooking into the FastMCP custom routes if available, or by adding a simple starlette route.

Replace the above with a simpler approach. Update `src/uvo_mcp/server.py` to include a custom health route via FastMCP's `custom_starlette_routes` if supported, or via a direct Starlette mount:

```python
"""FastMCP server definition with shared httpx client lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from uvo_mcp.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Shared application context available to all MCP tools via lifespan."""

    http_client: httpx.AsyncClient
    settings: Settings


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Create a shared httpx client for the lifetime of the MCP server."""
    settings = Settings()
    async with httpx.AsyncClient(
        base_url=settings.uvostat_base_url,
        headers={"ApiToken": settings.uvostat_api_token},
        timeout=settings.request_timeout,
    ) as client:
        logger.info("MCP server starting, httpx client ready")
        yield AppContext(http_client=client, settings=settings)
        logger.info("MCP server shutting down")


mcp = FastMCP(
    "UVO Search",
    description="Search Slovak government procurement data from UVOstat.sk and related sources",
    lifespan=app_lifespan,
    json_response=True,
)


# Health check endpoint -- accessible at GET /health
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check for container orchestration and monitoring."""
    return JSONResponse({"status": "ok", "service": "uvo-mcp"})


# Import tool modules to register @mcp.tool() decorators
import uvo_mcp.tools.procurements  # noqa: F401, E402
import uvo_mcp.tools.subjects  # noqa: F401, E402
```

Note: If `mcp.custom_route` is not available in the installed version, fall back to using the `mcp._app` Starlette app directly. Check the FastMCP API at runtime. A safe fallback implementation for `server.py`:

```python
"""FastMCP server definition with shared httpx client lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import FastMCP

from uvo_mcp.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Shared application context available to all MCP tools via lifespan."""

    http_client: httpx.AsyncClient
    settings: Settings


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Create a shared httpx client for the lifetime of the MCP server."""
    settings = Settings()
    async with httpx.AsyncClient(
        base_url=settings.uvostat_base_url,
        headers={"ApiToken": settings.uvostat_api_token},
        timeout=settings.request_timeout,
    ) as client:
        logger.info("MCP server starting, httpx client ready")
        yield AppContext(http_client=client, settings=settings)
        logger.info("MCP server shutting down")


mcp = FastMCP(
    "UVO Search",
    description="Search Slovak government procurement data from UVOstat.sk and related sources",
    lifespan=app_lifespan,
    json_response=True,
)


# Import tool modules to register @mcp.tool() decorators
import uvo_mcp.tools.procurements  # noqa: F401, E402
import uvo_mcp.tools.subjects  # noqa: F401, E402
```

And update `src/uvo_mcp/__main__.py` to add the health route at startup:

```python
"""Entry point for the UVO MCP server.

Usage:
    python -m uvo_mcp                  # streamable-http on port 8000 (default)
    python -m uvo_mcp stdio            # stdio transport for Claude Desktop/Code
"""

import sys


def main():
    from uvo_mcp.server import mcp

    transport = sys.argv[1] if len(sys.argv) > 1 else "streamable-http"
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # Add health check endpoint for HTTP transport
        from starlette.responses import JSONResponse

        @mcp.custom_route("/health", methods=["GET"])
        async def health_check(request):
            return JSONResponse({"status": "ok", "service": "uvo-mcp"})

        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
```

### Step 9.2 -- Test server imports cleanly and entry point works

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token uv run python -c "
from uvo_mcp.server import mcp, AppContext
print(f'Server name: {mcp.name}')
print(f'Tools registered: {len(mcp._tool_manager._tools) if hasattr(mcp, \"_tool_manager\") else \"unknown\"}')
print('OK: server imports and tools registered')
"
```

Expected output includes: `OK: server imports and tools registered`

### Step 9.3 -- Test server starts with streamable-http (manual verification)

- [ ] Start the server in background and test health check:

```bash
# Start server in background
UVOSTAT_API_TOKEN=test-token uv run python -m uvo_mcp &
SERVER_PID=$!
sleep 3

# Test health check
curl -s http://localhost:8000/health

# Clean up
kill $SERVER_PID 2>/dev/null
```

Expected: `{"status":"ok","service":"uvo-mcp"}` (or adapt if custom_route is not available -- the `/mcp` endpoint returning a response is also acceptable).

Note: If `mcp.custom_route` raises `AttributeError`, remove it and rely on the `/mcp` endpoint for health checking. Update the `__main__.py` accordingly. The important thing is that the server starts and listens on port 8000.

### Step 9.4 -- Commit

- [ ] Run:

```bash
git add src/uvo_mcp/server.py src/uvo_mcp/__main__.py
git commit -m "feat: add health check endpoint and verify MCP server startup"
```

---

## Task 10: NiceGUI Config

### Step 10.1 -- Write the failing test for GUI settings

- [ ] Create file `tests/gui/test_gui_config.py`:

```python
"""Tests for NiceGUI frontend configuration."""

import os
from unittest.mock import patch

import pytest


class TestGuiSettings:
    """Test that GuiSettings loads from environment variables."""

    def test_settings_loads_required_fields(self):
        """GuiSettings should load STORAGE_SECRET from env."""
        env = {
            "STORAGE_SECRET": "test-secret-abc",
            "UVOSTAT_API_TOKEN": "dummy",
        }
        with patch.dict(os.environ, env, clear=False):
            from uvo_gui.config import GuiSettings

            s = GuiSettings()
            assert s.storage_secret == "test-secret-abc"

    def test_settings_default_values(self):
        """GuiSettings should have sensible defaults."""
        env = {
            "STORAGE_SECRET": "test-secret",
            "UVOSTAT_API_TOKEN": "dummy",
        }
        with patch.dict(os.environ, env, clear=False):
            from uvo_gui.config import GuiSettings

            s = GuiSettings()
            assert s.mcp_server_url == "http://localhost:8000/mcp"
            assert s.gui_host == "0.0.0.0"
            assert s.gui_port == 8080

    def test_settings_override_from_env(self):
        """GuiSettings should pick up overridden values."""
        env = {
            "STORAGE_SECRET": "test-secret",
            "UVOSTAT_API_TOKEN": "dummy",
            "MCP_SERVER_URL": "http://mcp-server:8000/mcp",
            "GUI_PORT": "9090",
        }
        with patch.dict(os.environ, env, clear=False):
            from uvo_gui.config import GuiSettings

            s = GuiSettings()
            assert s.mcp_server_url == "http://mcp-server:8000/mcp"
            assert s.gui_port == 9090

    def test_missing_storage_secret_raises(self):
        """GuiSettings should raise when STORAGE_SECRET is missing."""
        from pydantic import ValidationError
        from uvo_gui.config import GuiSettings

        env_without = {
            k: v
            for k, v in os.environ.items()
            if k != "STORAGE_SECRET"
        }
        with patch.dict(os.environ, env_without, clear=True):
            with pytest.raises(ValidationError):
                GuiSettings()
```

### Step 10.2 -- Run the test to confirm it fails

- [ ] Run:

```bash
uv run pytest tests/gui/test_gui_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'uvo_gui.config'`.

### Step 10.3 -- Implement GUI config

- [ ] Create file `src/uvo_gui/config.py`:

```python
"""NiceGUI frontend configuration via environment variables."""

from pydantic_settings import BaseSettings


class GuiSettings(BaseSettings):
    """Configuration for the UVO Search NiceGUI frontend.

    All fields map to environment variables of the same name (uppercase).
    """

    mcp_server_url: str = "http://localhost:8000/mcp"
    storage_secret: str
    gui_host: str = "0.0.0.0"
    gui_port: int = 8080

    model_config = {"env_file": ".env", "env_prefix": ""}
```

### Step 10.4 -- Run the tests to confirm they pass

- [ ] Run:

```bash
uv run pytest tests/gui/test_gui_config.py -v
```

Expected: all 4 tests pass (`4 passed`).

### Step 10.5 -- Commit

- [ ] Run:

```bash
git add src/uvo_gui/config.py tests/gui/test_gui_config.py
git commit -m "feat: add NiceGUI frontend GuiSettings with mcp_server_url and storage_secret"
```

---

## Task 11: MCP Client Wrapper (TDD)

### Step 11.1 -- Write the failing test for call_tool

- [ ] Create file `tests/gui/test_mcp_client.py`:

```python
"""Tests for the MCP client wrapper."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCallTool:
    """Tests for the call_tool function."""

    @pytest.mark.asyncio
    async def test_call_tool_returns_parsed_json(self):
        """call_tool should parse the TextContent from MCP response into a dict."""
        expected_data = {
            "summary": {"total_records": 1, "offset": 0, "limit": 20},
            "data": [{"id": "1", "nazov": "Test"}],
        }

        # Mock the MCP session and its call_tool method
        mock_session = AsyncMock()
        mock_text_content = MagicMock()
        mock_text_content.text = json.dumps(expected_data)
        mock_result = MagicMock()
        mock_result.content = [mock_text_content]
        mock_session.call_tool.return_value = mock_result
        mock_session.initialize = AsyncMock()

        # Mock the streamablehttp_client context manager
        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_get_url = AsyncMock()

        with (
            patch("uvo_gui.mcp_client.streamablehttp_client") as mock_transport,
            patch("uvo_gui.mcp_client.ClientSession") as mock_client_session_cls,
        ):
            # Setup the async context managers
            mock_transport.return_value.__aenter__ = AsyncMock(
                return_value=(mock_read, mock_write, mock_get_url)
            )
            mock_transport.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_client_session_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_client_session_cls.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            from uvo_gui.mcp_client import call_tool

            result = await call_tool(
                "search_completed_procurements",
                {"text_query": "IT", "limit": 20, "offset": 0},
            )

        assert result == expected_data
        mock_session.call_tool.assert_called_once_with(
            "search_completed_procurements",
            {"text_query": "IT", "limit": 20, "offset": 0},
        )

    @pytest.mark.asyncio
    async def test_call_tool_raises_on_no_text_content(self):
        """call_tool should raise ValueError if response has no text content."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.content = []  # No content
        mock_session.call_tool.return_value = mock_result
        mock_session.initialize = AsyncMock()

        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_get_url = AsyncMock()

        with (
            patch("uvo_gui.mcp_client.streamablehttp_client") as mock_transport,
            patch("uvo_gui.mcp_client.ClientSession") as mock_client_session_cls,
        ):
            mock_transport.return_value.__aenter__ = AsyncMock(
                return_value=(mock_read, mock_write, mock_get_url)
            )
            mock_transport.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_client_session_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_client_session_cls.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            from uvo_gui.mcp_client import call_tool

            with pytest.raises(ValueError, match="No text content"):
                await call_tool("some_tool", {})
```

### Step 11.2 -- Run the test to confirm it fails

- [ ] Run:

```bash
uv run pytest tests/gui/test_mcp_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'uvo_gui.mcp_client'`.

### Step 11.3 -- Implement mcp_client.py

- [ ] Create file `src/uvo_gui/mcp_client.py`:

```python
"""MCP client wrapper for calling MCP server tools from the NiceGUI frontend."""

import json
import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from uvo_gui.config import GuiSettings

logger = logging.getLogger(__name__)

_settings = GuiSettings()


async def call_tool(tool_name: str, arguments: dict) -> dict:
    """Call an MCP tool on the server and return the parsed result.

    Args:
        tool_name: Name of the MCP tool to call (e.g. 'search_completed_procurements').
        arguments: Dictionary of arguments to pass to the tool.

    Returns:
        Parsed JSON dict from the tool's text response.

    Raises:
        ValueError: If the MCP response contains no text content.
        Exception: On connection or protocol errors.
    """
    logger.info("Calling MCP tool: %s", tool_name)
    async with streamablehttp_client(_settings.mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            for content in result.content:
                if hasattr(content, "text"):
                    return json.loads(content.text)
            raise ValueError(f"No text content in response from {tool_name}")
```

### Step 11.4 -- Run the tests to confirm they pass

- [ ] Run:

```bash
STORAGE_SECRET=test-secret uv run pytest tests/gui/test_mcp_client.py -v
```

Expected: all 2 tests pass (`2 passed`).

### Step 11.5 -- Commit

- [ ] Run:

```bash
git add src/uvo_gui/mcp_client.py tests/gui/test_mcp_client.py
git commit -m "feat: add MCP client wrapper for NiceGUI frontend to call MCP server tools"
```

---

## Task 12: Navigation Header Component

### Step 12.1 -- Create the nav_header component

- [ ] Create file `src/uvo_gui/components/nav_header.py`:

```python
"""Shared navigation header component for all pages."""

from nicegui import ui


def nav_header() -> None:
    """Render the application navigation header.

    Shows the app name and links to main pages. Present on every page.
    """
    with ui.header().classes("bg-blue-800 text-white"):
        with ui.row().classes("w-full max-w-screen-xl mx-auto items-center"):
            ui.label("UVO Search").classes(
                "text-xl font-bold cursor-pointer"
            ).on("click", lambda: ui.navigate.to("/"))
            ui.space()
            with ui.row().classes("gap-4"):
                ui.link("Vyhladavanie", "/").classes("text-white")
                ui.link("Obstaravatelia", "/procurers").classes("text-white")
                ui.link("Dodavatelia", "/suppliers").classes("text-white")
                ui.link("O aplikacii", "/about").classes("text-white")
```

### Step 12.2 -- Commit

- [ ] Run:

```bash
git add src/uvo_gui/components/nav_header.py
git commit -m "feat: add navigation header component with links to all pages"
```

---

## Task 13: Main Search Page

### Step 13.1 -- Create the SearchState class and search page

- [ ] Create file `src/uvo_gui/pages/search.py`:

```python
"""Main search page for UVO procurement data."""

import logging

from nicegui import ui

from uvo_gui.components.nav_header import nav_header
from uvo_gui import mcp_client

logger = logging.getLogger(__name__)


class SearchState:
    """Manages search form state and results for the main search page."""

    def __init__(self):
        self.query: str = ""
        self.date_from: str = ""
        self.date_to: str = ""
        self.results: list[dict] = []
        self.total: int = 0
        self.page: int = 1
        self.per_page: int = 20
        self.loading: bool = False
        self.error: str | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def total_pages(self) -> int:
        if self.total == 0:
            return 1
        return (self.total + self.per_page - 1) // self.per_page

    async def search(self) -> None:
        """Execute search and update results. Resets to page 1."""
        self.page = 1
        await self._fetch()

    async def goto_page(self, page: int) -> None:
        """Navigate to a specific page number."""
        self.page = max(1, min(page, self.total_pages))
        await self._fetch()

    async def _fetch(self) -> None:
        """Fetch results from MCP server for current page."""
        self.loading = True
        self.error = None
        self.results_view.refresh()

        try:
            arguments: dict = {
                "limit": self.per_page,
                "offset": self.offset,
            }
            if self.query:
                arguments["text_query"] = self.query
            if self.date_from:
                arguments["date_from"] = self.date_from
            if self.date_to:
                arguments["date_to"] = self.date_to

            data = await mcp_client.call_tool(
                "search_completed_procurements", arguments
            )

            if "error" in data:
                self.error = data["error"]
                self.results = []
                self.total = 0
            else:
                self.results = data.get("data", [])
                self.total = data.get("summary", {}).get("total_records", 0)
        except Exception as exc:
            logger.error("Search failed: %s", exc)
            self.error = str(exc)
            self.results = []
            self.total = 0
        finally:
            self.loading = False
            self.results_view.refresh()

    @ui.refreshable
    def results_view(self) -> None:
        """Render the search results area (table + pagination)."""
        if self.loading:
            with ui.row().classes("w-full justify-center my-8"):
                ui.spinner("dots", size="xl")
            return

        if self.error:
            ui.label(f"Chyba: {self.error}").classes("text-red-500 my-4")
            return

        if not self.results:
            ui.label("Ziadne vysledky").classes("text-gray-500 my-4")
            return

        # Results count
        ui.label(f"Najdenych: {self.total:,} zaznamov").classes("text-sm text-gray-600 mb-2")

        # Results table
        columns = [
            {"name": "id", "label": "ID", "field": "id", "align": "left", "sortable": True},
            {"name": "nazov", "label": "Nazov", "field": "nazov", "align": "left", "sortable": True},
            {"name": "obstaravatel_nazov", "label": "Obstaravatel", "field": "obstaravatel_nazov", "align": "left", "sortable": True},
            {"name": "konecna_hodnota", "label": "Hodnota (EUR)", "field": "konecna_hodnota", "align": "right", "sortable": True},
            {"name": "datum_zverejnenia", "label": "Datum", "field": "datum_zverejnenia", "align": "left", "sortable": True},
            {"name": "cpv_kod", "label": "CPV", "field": "cpv_kod", "align": "left"},
            {"name": "stav", "label": "Stav", "field": "stav", "align": "left"},
        ]

        table = ui.table(
            columns=columns,
            rows=self.results,
            row_key="id",
        ).classes("w-full")

        table.on("row-click", lambda e: self._on_row_click(e.args[1]))

        # Pagination controls
        with ui.row().classes("w-full justify-center items-center mt-4 gap-2"):
            ui.button(
                icon="chevron_left",
                on_click=lambda: self.goto_page(self.page - 1),
            ).props("flat dense").bind_enabled_from(self, "page", lambda p: p > 1)

            ui.label().bind_text_from(
                self, "page", lambda p: f"Strana {p} z {self.total_pages}"
            )

            ui.button(
                icon="chevron_right",
                on_click=lambda: self.goto_page(self.page + 1),
            ).props("flat dense").bind_enabled_from(
                self, "page", lambda p: p < self.total_pages
            )

    def _on_row_click(self, row: dict) -> None:
        """Handle row click -- show detail dialog."""
        from uvo_gui.components.detail_dialog import show_detail_dialog

        show_detail_dialog(row)


@ui.page("/")
def search_page() -> None:
    """Main search page."""
    nav_header()
    state = SearchState()

    with ui.column().classes("w-full max-w-screen-xl mx-auto p-4"):
        ui.label("Vyhladavanie v obstaravaniach").classes("text-2xl font-bold mb-4")

        # Search form
        with ui.card().classes("w-full mb-4"):
            with ui.row().classes("w-full items-end gap-4 flex-wrap"):
                query_input = ui.input(
                    label="Hladany vyraz",
                    placeholder="Zadajte hladany text...",
                ).classes("flex-grow").on(
                    "keydown.enter", lambda: state.search()
                )
                query_input.bind_value(state, "query")

                ui.button("Hladat", on_click=state.search).props("color=primary")

            with ui.row().classes("w-full items-end gap-4 mt-2"):
                date_from_input = ui.input(
                    label="Datum od",
                    placeholder="YYYY-MM-DD",
                ).classes("w-40")
                date_from_input.bind_value(state, "date_from")

                date_to_input = ui.input(
                    label="Datum do",
                    placeholder="YYYY-MM-DD",
                ).classes("w-40")
                date_to_input.bind_value(state, "date_to")

        # Results area
        state.results_view()
```

### Step 13.2 -- Commit

- [ ] Run:

```bash
git add src/uvo_gui/pages/search.py
git commit -m "feat: add main search page with SearchState, results table, and pagination"
```

---

## Task 14: Detail Dialog Component

### Step 14.1 -- Create the detail dialog

- [ ] Create file `src/uvo_gui/components/detail_dialog.py`:

```python
"""Procurement detail dialog component (shown on row click)."""

from nicegui import ui


def show_detail_dialog(procurement: dict) -> None:
    """Show a modal dialog with key procurement details.

    Args:
        procurement: Dict of procurement data from search results.
    """
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl"):
        # Title
        ui.label(procurement.get("nazov", "Bez nazvu")).classes("text-xl font-bold")
        ui.separator()

        # Key fields in a grid
        with ui.grid(columns=2).classes("w-full gap-2"):
            _field("ID", procurement.get("id", "-"))
            _field("Stav", procurement.get("stav", "-"))
            _field("Obstaravatel", procurement.get("obstaravatel_nazov", "-"))
            _field("ICO obstaravatela", procurement.get("obstaravatel_ico", "-"))
            _field(
                "Predpokladana hodnota",
                _format_value(procurement.get("predpokladana_hodnota")),
            )
            _field(
                "Konecna hodnota",
                _format_value(procurement.get("konecna_hodnota")),
            )
            _field("Datum vyhlasenia", procurement.get("datum_vyhlasenia", "-"))
            _field("Datum zverejnenia", procurement.get("datum_zverejnenia", "-"))
            _field("CPV kod", procurement.get("cpv_kod", "-"))
            _field("Typ postupu", procurement.get("typ_postupu", "-"))

        # Suppliers section
        dodavatelia = procurement.get("dodavatelia", [])
        if dodavatelia:
            ui.separator()
            ui.label("Dodavatelia").classes("font-bold mt-2")
            for d in dodavatelia:
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label(d.get("nazov", "-")).classes("font-medium")
                    if d.get("ico"):
                        ui.label(f"ICO: {d['ico']}").classes("text-sm text-gray-600")
                    if d.get("hodnota") is not None:
                        ui.label(_format_value(d["hodnota"])).classes(
                            "text-sm text-green-700"
                        )

        # Action buttons
        with ui.row().classes("w-full justify-end mt-4 gap-2"):
            ui.button("Zavriet", on_click=dialog.close).props("flat")

    dialog.open()


def _field(label: str, value: str) -> None:
    """Render a label-value pair in the detail grid."""
    ui.label(label).classes("text-sm text-gray-500")
    ui.label(str(value)).classes("text-sm font-medium")


def _format_value(value: float | None) -> str:
    """Format a monetary value for display."""
    if value is None:
        return "-"
    return f"{value:,.2f} EUR"
```

### Step 14.2 -- Commit

- [ ] Run:

```bash
git add src/uvo_gui/components/detail_dialog.py
git commit -m "feat: add procurement detail dialog component for row-click display"
```

---

## Task 15: NiceGUI App Entry Point

### Step 15.1 -- Create app.py

- [ ] Create file `src/uvo_gui/app.py`:

```python
"""NiceGUI application setup and configuration."""

import logging

from nicegui import app, ui

from uvo_gui.config import GuiSettings

logger = logging.getLogger(__name__)


def create_app() -> None:
    """Configure and register all pages for the NiceGUI application."""
    settings = GuiSettings()

    # Set storage secret for user session persistence
    app.storage.secret = settings.storage_secret

    # Import pages to register their @ui.page() decorators
    import uvo_gui.pages.search  # noqa: F401

    logger.info("NiceGUI app configured with MCP server at %s", settings.mcp_server_url)


def run() -> None:
    """Start the NiceGUI application."""
    settings = GuiSettings()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    create_app()

    ui.run(
        title="UVO Search",
        host=settings.gui_host,
        port=settings.gui_port,
        reload=False,
        show=False,
    )
```

### Step 15.2 -- Create __main__.py

- [ ] Create file `src/uvo_gui/__main__.py`:

```python
"""Entry point for the UVO Search NiceGUI frontend.

Usage:
    python -m uvo_gui
"""

from uvo_gui.app import run


def main():
    run()


if __name__ == "__main__":
    main()
```

### Step 15.3 -- Test the app can be imported without errors

- [ ] Run:

```bash
STORAGE_SECRET=test-secret uv run python -c "from uvo_gui.app import create_app; print('OK: GUI app imports cleanly')"
```

Expected: `OK: GUI app imports cleanly`

### Step 15.4 -- Commit

- [ ] Run:

```bash
git add src/uvo_gui/app.py src/uvo_gui/__main__.py
git commit -m "feat: add NiceGUI app entry point with page registration and storage config"
```

---

## Task 16: Run All Tests and Final Validation

### Step 16.1 -- Run the full test suite

- [ ] Run:

```bash
UVOSTAT_API_TOKEN=test-token STORAGE_SECRET=test-secret uv run pytest tests/ -v --tb=short
```

Expected: all tests pass (approximately 29 tests):
- `tests/mcp/test_config.py` -- 4 passed
- `tests/mcp/test_models.py` -- 12 passed
- `tests/mcp/test_tools_procurements.py` -- 9 passed
- `tests/mcp/test_tools_subjects.py` -- 8 passed
- `tests/gui/test_gui_config.py` -- 4 passed
- `tests/gui/test_mcp_client.py` -- 2 passed

### Step 16.2 -- Manual end-to-end validation steps

- [ ] Document and execute these manual verification steps:

**Start the MCP server:**

```bash
# Terminal 1
UVOSTAT_API_TOKEN=<your-real-token> uv run python -m uvo_mcp
# Expected: server starts on port 8000, logs "MCP server starting"
```

**Start the NiceGUI frontend:**

```bash
# Terminal 2
STORAGE_SECRET=some-secret-string MCP_SERVER_URL=http://localhost:8000/mcp uv run python -m uvo_gui
# Expected: NiceGUI starts on port 8080, logs "NiceGUI app configured"
```

**Verify in browser:**

1. Open `http://localhost:8080/` -- search page should load with header and search form
2. Enter a search term (e.g., "IT") and click "Hladat" -- results should appear in the table
3. Click pagination arrows -- next page of results should load
4. Click a table row -- detail dialog should open with procurement info
5. Click "Zavriet" -- dialog should close

**Verify MCP server directly (optional):**

```bash
# Test with Claude Code by adding to .claude/mcp.json:
# { "mcpServers": { "uvo": { "command": "uv", "args": ["run", "python", "-m", "uvo_mcp", "stdio"], "env": { "UVOSTAT_API_TOKEN": "<token>" } } } }
```

### Step 16.3 -- Final commit

- [ ] Run:

```bash
git add -A
git commit -m "feat: complete Phase 1 MVP -- MCP server with 4 tools + NiceGUI search frontend"
```

---

## Summary of All Files Created

| File | Lines (approx) | Purpose |
|------|----------------|---------|
| `pyproject.toml` | 40 | Project config, deps, scripts |
| `.env.example` | 20 | Environment variable template |
| `.gitignore` | 20 | Git ignore patterns |
| `src/uvo_mcp/__init__.py` | 0 | Package marker |
| `src/uvo_mcp/__main__.py` | 25 | MCP server entry point |
| `src/uvo_mcp/config.py` | 20 | Server settings (pydantic-settings) |
| `src/uvo_mcp/models.py` | 80 | Pydantic data models |
| `src/uvo_mcp/server.py` | 50 | FastMCP, AppContext, lifespan |
| `src/uvo_mcp/tools/__init__.py` | 0 | Package marker |
| `src/uvo_mcp/tools/procurements.py` | 110 | 2 procurement tools |
| `src/uvo_mcp/tools/subjects.py` | 100 | 2 subject tools |
| `src/uvo_gui/__init__.py` | 0 | Package marker |
| `src/uvo_gui/__main__.py` | 15 | GUI entry point |
| `src/uvo_gui/app.py` | 40 | NiceGUI app setup |
| `src/uvo_gui/config.py` | 15 | GUI settings |
| `src/uvo_gui/mcp_client.py` | 35 | MCP client wrapper |
| `src/uvo_gui/pages/__init__.py` | 0 | Package marker |
| `src/uvo_gui/pages/search.py` | 170 | Main search page |
| `src/uvo_gui/components/__init__.py` | 0 | Package marker |
| `src/uvo_gui/components/nav_header.py` | 20 | Navigation header |
| `src/uvo_gui/components/detail_dialog.py` | 70 | Detail dialog |
| `tests/__init__.py` | 0 | Package marker |
| `tests/conftest.py` | 55 | Shared fixtures |
| `tests/mcp/__init__.py` | 0 | Package marker |
| `tests/mcp/test_config.py` | 60 | Config tests |
| `tests/mcp/test_models.py` | 130 | Model tests |
| `tests/mcp/test_tools_procurements.py` | 180 | Procurement tool tests |
| `tests/mcp/test_tools_subjects.py` | 160 | Subject tool tests |
| `tests/gui/__init__.py` | 0 | Package marker |
| `tests/gui/test_gui_config.py` | 55 | GUI config tests |
| `tests/gui/test_mcp_client.py` | 80 | MCP client tests |

**Total:** 31 files, ~1,550 lines of code and tests.

## Commit History (Expected)

1. `chore: scaffold project structure with dependencies and empty packages`
2. `feat: add MCP server Settings with pydantic-settings and full test coverage`
3. `feat: add Pydantic data models for procurement, subject, and pagination`
4. `feat: add MCP server core with FastMCP, AppContext lifespan, and entry point`
5. `feat: add search_completed_procurements MCP tool with full test coverage`
6. `feat: add get_procurement_detail MCP tool with not-found and error handling`
7. `feat: add find_procurer MCP tool for searching contracting authorities`
8. `feat: add find_supplier MCP tool for searching procurement suppliers`
9. `feat: add health check endpoint and verify MCP server startup`
10. `feat: add NiceGUI frontend GuiSettings with mcp_server_url and storage_secret`
11. `feat: add MCP client wrapper for NiceGUI frontend to call MCP server tools`
12. `feat: add navigation header component with links to all pages`
13. `feat: add main search page with SearchState, results table, and pagination`
14. `feat: add procurement detail dialog component for row-click display`
15. `feat: add NiceGUI app entry point with page registration and storage config`
16. `feat: complete Phase 1 MVP -- MCP server with 4 tools + NiceGUI search frontend`
