# NiceGUI UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the NiceGUI frontend with a persistent Quasar sidebar layout, light theme, split-panel search page, and three new subpages (Obstaravatelia, Dodavatelia, O aplikácii).

**Architecture:** A shared `layout()` context manager in `components/layout.py` uses NiceGUI's Quasar primitives (`ui.left_drawer`, `ui.header`, `ui.page_container`) to render the sidebar on every page. Each page imports `layout` and renders its content inside it. The search page is rebuilt with a two-column split panel (left: search form + result list; right: detail view) instead of a table + dialog.

**Tech Stack:** Python, NiceGUI (Quasar under the hood), `mcp_client.call_tool()` for all backend calls, pytest + `nicegui.testing` for unit tests.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/uvo_gui/components/layout.py` | Quasar sidebar shell, active nav highlighting |
| Delete | `src/uvo_gui/components/nav_header.py` | Replaced by layout.py |
| Delete | `src/uvo_gui/components/detail_dialog.py` | Replaced by inline detail panel in search.py |
| Rewrite | `src/uvo_gui/pages/search.py` | Split-panel search: left list + right detail |
| Create | `src/uvo_gui/pages/procurers.py` | Obstaravatelia: search + card grid |
| Create | `src/uvo_gui/pages/suppliers.py` | Dodavatelia: search + card grid |
| Create | `src/uvo_gui/pages/about.py` | O aplikácii: minimal text page |
| Modify | `src/uvo_gui/app.py` | Register 3 new routes, remove nav_header import |
| Create | `tests/gui/test_layout.py` | Tests for layout component |
| Create | `tests/gui/test_search_page.py` | Tests for split-panel search page |
| Create | `tests/gui/test_procurers_page.py` | Tests for procurers page |
| Create | `tests/gui/test_suppliers_page.py` | Tests for suppliers page |
| Create | `tests/gui/test_about_page.py` | Tests for about page |

---

## Task 1: Create shared layout component

**Files:**
- Create: `src/uvo_gui/components/layout.py`
- Create: `tests/gui/test_layout.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/gui/test_layout.py
"""Tests for the shared Quasar layout component."""
from unittest.mock import patch

import pytest
from nicegui.testing import User


@pytest.mark.asyncio
async def test_layout_renders_app_name(user: User) -> None:
    from uvo_gui.components import layout  # noqa: F401 — triggers page registration
    await user.open("/")
    await user.should_contain("UVO Search")


@pytest.mark.asyncio
async def test_layout_renders_all_nav_links(user: User) -> None:
    from uvo_gui.components import layout  # noqa: F401
    await user.open("/")
    await user.should_contain("Vyhľadávanie")
    await user.should_contain("Obstaravatelia")
    await user.should_contain("Dodavatelia")
    await user.should_contain("O aplikácii")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/max/Documents/src/uvo-search
pytest tests/gui/test_layout.py -v
```

Expected: `FAILED` — `ModuleNotFoundError` or `ImportError` for `uvo_gui.components.layout`

- [ ] **Step 3: Create `src/uvo_gui/components/layout.py`**

```python
"""Shared Quasar layout shell — sidebar + page container."""

from contextlib import contextmanager
from typing import Generator

from nicegui import ui

NAV_ITEMS = [
    ("🔍", "Vyhľadávanie", "/"),
    ("🏢", "Obstaravatelia", "/procurers"),
    ("🤝", "Dodavatelia", "/suppliers"),
    ("ℹ️", "O aplikácii", "/about"),
]


@contextmanager
def layout(current_path: str = "/") -> Generator[None, None, None]:
    """Render the Quasar app shell (header + sidebar + page container).

    Usage::

        @ui.page("/some-route")
        async def my_page() -> None:
            with layout(current_path="/some-route"):
                ui.label("page content")
    """
    with ui.header().classes("bg-white border-b border-slate-200 px-4 h-12 flex items-center"):
        ui.label("UVO Search").classes("text-blue-700 font-bold text-base")
        ui.label("Vestník verejného obstarávania").classes("text-slate-400 text-xs ml-2")

    with ui.left_drawer(value=True).classes("bg-white border-r border-slate-200 pt-4 w-48"):
        ui.label("Navigácia").classes("text-xs font-semibold text-slate-400 uppercase px-3 mb-2")
        for icon, label, path in NAV_ITEMS:
            active = current_path == path
            classes = (
                "flex items-center gap-2 px-3 py-2 rounded-md text-sm mb-1 cursor-pointer w-full text-left "
            )
            if active:
                classes += "bg-blue-100 text-blue-700 font-medium"
            else:
                classes += "text-slate-500 hover:bg-slate-100"
            ui.button(
                f"{icon} {label}",
                on_click=lambda p=path: ui.navigate.to(p),
            ).classes(classes).props("flat no-caps")

    with ui.page_container():
        yield
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/gui/test_layout.py -v
```

Expected: both tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/uvo_gui/components/layout.py tests/gui/test_layout.py
git commit -m "feat: add shared Quasar sidebar layout component"
```

---

## Task 2: Rewrite search page with split panel

**Files:**
- Rewrite: `src/uvo_gui/pages/search.py`
- Create: `tests/gui/test_search_page.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui/test_search_page.py
"""Tests for the split-panel search page."""
from unittest.mock import AsyncMock, patch

import pytest
from nicegui.testing import User


MOCK_RESULTS = {
    "items": [
        {
            "id": "1",
            "nazov": "Stavebné práce",
            "obstaravatel_nazov": "MV SR",
            "konecna_hodnota": 120000,
            "datum_zverejnenia": "2024-01-15",
            "cpv_kod": "45100000-8",
            "stav": "Zadaná zákazka",
            "dodavatelia": [{"nazov": "ACME s.r.o.", "ico": "12345678"}],
        }
    ],
    "total": 1,
}


@pytest.mark.asyncio
async def test_search_page_shows_search_form(user: User) -> None:
    import uvo_gui.pages.search  # noqa: F401
    await user.open("/")
    await user.should_contain("Hľadať zákazku")
    await user.should_contain("Hľadať")


@pytest.mark.asyncio
async def test_search_page_shows_empty_state(user: User) -> None:
    import uvo_gui.pages.search  # noqa: F401
    await user.open("/")
    await user.should_contain("Vyberte zákazku zo zoznamu")


@pytest.mark.asyncio
async def test_search_page_shows_results_after_search(user: User) -> None:
    import uvo_gui.pages.search  # noqa: F401
    with patch(
        "uvo_gui.mcp_client.call_tool",
        new_callable=AsyncMock,
        return_value=MOCK_RESULTS,
    ):
        await user.open("/")
        await user.should_contain("Hľadať")
        user.find("Hľadať").click()
        await user.should_contain("Stavebné práce")


@pytest.mark.asyncio
async def test_search_page_shows_detail_on_click(user: User) -> None:
    import uvo_gui.pages.search  # noqa: F401
    with patch(
        "uvo_gui.mcp_client.call_tool",
        new_callable=AsyncMock,
        return_value=MOCK_RESULTS,
    ):
        await user.open("/")
        user.find("Hľadať").click()
        await user.should_contain("Stavebné práce")
        user.find("Stavebné práce").click()
        await user.should_contain("MV SR")
        await user.should_contain("ACME s.r.o.")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/gui/test_search_page.py -v
```

Expected: `FAILED` — tests import old search.py which has different structure

- [ ] **Step 3: Rewrite `src/uvo_gui/pages/search.py`**

```python
"""Search page — split panel: left result list, right detail view."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui

from uvo_gui import mcp_client
from uvo_gui.components.layout import layout

logger = logging.getLogger(__name__)


@dataclass
class SearchState:
    """Search parameters, results, pagination, and selected item."""

    query: str = ""
    date_from: str = ""
    date_to: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    loading: bool = False
    error: str = ""
    selected: dict[str, Any] | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def total_pages(self) -> int:
        return max(1, -(-self.total // self.per_page))

    async def search(self) -> None:
        self.page = 1
        self.selected = None
        await self._fetch()

    async def goto_page(self, page: int) -> None:
        self.page = max(1, min(page, self.total_pages))
        self.selected = None
        await self._fetch()

    async def _fetch(self) -> None:
        self.loading = True
        self.error = ""
        list_view.refresh()
        detail_view.refresh()
        try:
            arguments: dict[str, Any] = {"limit": self.per_page, "offset": self.offset}
            if self.query:
                arguments["q"] = self.query
            if self.date_from:
                arguments["date_from"] = self.date_from
            if self.date_to:
                arguments["date_to"] = self.date_to
            data = await mcp_client.call_tool("search_completed_procurements", arguments)
            self.results = data.get("items", [])
            self.total = data.get("total", 0)
        except Exception as exc:  # noqa: BLE001
            logger.error("Search failed: %s", exc)
            self.error = f"Chyba pri vyhľadávaní: {exc}"
            self.results = []
            self.total = 0
        finally:
            self.loading = False
            list_view.refresh()
            detail_view.refresh()

    def select(self, item: dict[str, Any]) -> None:
        self.selected = item
        detail_view.refresh()


_state = SearchState()


@ui.refreshable
def list_view() -> None:
    """Left panel: search form + scrollable result list + pagination."""
    with ui.card().classes("w-full h-full"):
        # Search form
        ui.label("Hľadať zákazku").classes("text-sm font-semibold text-slate-700 mb-2")
        ui.input(placeholder="🔍 Kľúčové slovo...").classes("w-full mb-2").bind_value(
            _state, "query"
        )
        with ui.row().classes("w-full gap-2 mb-2"):
            ui.input(placeholder="Od dátumu").classes("flex-1").bind_value(_state, "date_from")
            ui.input(placeholder="Do dátumu").classes("flex-1").bind_value(_state, "date_to")
        ui.button("Hľadať", on_click=_state.search).classes(
            "w-full bg-blue-700 text-white"
        ).props("no-caps")

    if _state.loading:
        with ui.row().classes("justify-center py-6"):
            ui.spinner(size="md")
        return

    if _state.error:
        ui.label(_state.error).classes("text-red-600 text-sm py-2")
        return

    if not _state.results:
        return

    ui.label(f"Výsledky: {_state.total}").classes("text-xs text-slate-500 mt-2 mb-1")

    with ui.scroll_area().classes("flex-1"):
        for item in _state.results:
            selected = _state.selected and _state.selected.get("id") == item.get("id")
            card_classes = (
                "w-full mb-1 cursor-pointer border-l-4 "
                + ("border-blue-600 bg-blue-50" if selected else "border-transparent hover:bg-slate-50")
            )
            with ui.card().classes(card_classes).on("click", lambda i=item: _state.select(i)):
                ui.label(item.get("nazov", "-")).classes(
                    "text-sm font-semibold " + ("text-blue-700" if selected else "text-slate-800")
                )
                with ui.row().classes("gap-3 flex-wrap"):
                    ui.label(f"🏢 {item.get('obstaravatel_nazov', '-')}").classes(
                        "text-xs text-slate-500"
                    )
                    ui.label(f"{item.get('konecna_hodnota', '-')} €").classes(
                        "text-xs text-green-700 font-semibold"
                    )
                    ui.label(str(item.get("datum_zverejnenia", "-"))).classes(
                        "text-xs text-slate-500"
                    )

    # Pagination
    with ui.row().classes("items-center justify-between mt-2"):
        ui.button(
            "← Predch.",
            on_click=lambda: ui.timer(0, lambda: _state.goto_page(_state.page - 1), once=True),
        ).props("flat no-caps").classes("text-xs").set_enabled(_state.page > 1)
        ui.label(f"{_state.page} / {_state.total_pages}").classes("text-xs text-slate-500")
        ui.button(
            "Ďalšia →",
            on_click=lambda: ui.timer(0, lambda: _state.goto_page(_state.page + 1), once=True),
        ).props("flat no-caps").classes("text-xs text-blue-600").set_enabled(
            _state.page < _state.total_pages
        )


@ui.refreshable
def detail_view() -> None:
    """Right panel: detail of the selected procurement."""
    if _state.selected is None:
        with ui.column().classes("items-center justify-center h-full text-slate-400 gap-2"):
            ui.label("Vyberte zákazku zo zoznamu").classes("text-sm")
        return

    item = _state.selected
    ui.label(item.get("nazov", "-")).classes("text-lg font-semibold text-slate-800 mb-2")

    # Badges
    with ui.row().classes("gap-2 mb-4 flex-wrap"):
        if item.get("cpv_kod"):
            ui.badge(item["cpv_kod"]).classes("bg-blue-100 text-blue-700 text-xs")
        if item.get("stav"):
            ui.badge(item["stav"]).classes("bg-green-100 text-green-700 text-xs")

    # Info grid
    with ui.grid(columns=2).classes("w-full gap-3 mb-4"):
        for label, key, formatter in [
            ("Obstarávateľ", "obstaravatel_nazov", str),
            ("Hodnota", "konecna_hodnota", lambda v: f"{v} €"),
            ("Dátum", "datum_zverejnenia", str),
            ("CPV kód", "cpv_kod", str),
        ]:
            with ui.card().classes("bg-slate-50 border-0"):
                ui.label(label).classes("text-xs text-slate-500 mb-1")
                value = item.get(key, "-")
                display = formatter(value) if value and value != "-" else "-"
                extra = "text-green-700 font-bold text-base" if key == "konecna_hodnota" else "text-sm font-semibold text-slate-800"
                ui.label(display).classes(extra)

    # Suppliers
    dodavatelia = item.get("dodavatelia", [])
    if dodavatelia:
        ui.label("Dodávatelia").classes("text-sm font-semibold text-slate-700 mb-2")
        for supplier in dodavatelia:
            with ui.card().classes("w-full bg-slate-50 border-0 mb-1"):
                with ui.row().classes("items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label(supplier.get("nazov", "-")).classes(
                            "text-sm font-semibold text-slate-800"
                        )
                        ui.label(f"IČO: {supplier.get('ico', '-')}").classes(
                            "text-xs text-slate-500"
                        )
                    ui.badge("Víťaz").classes("bg-blue-100 text-blue-700 text-xs")


@ui.page("/")
async def search_page() -> None:
    """Split-panel search page."""
    with layout(current_path="/"):
        with ui.row().classes("w-full h-full gap-4 p-4"):
            with ui.column().classes("w-72 flex-shrink-0 h-full"):
                list_view()
            with ui.column().classes("flex-1 h-full"):
                with ui.card().classes("w-full h-full p-4"):
                    detail_view()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/gui/test_search_page.py -v
```

Expected: all 4 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/uvo_gui/pages/search.py tests/gui/test_search_page.py
git commit -m "feat: rewrite search page with split-panel layout"
```

---

## Task 3: Create Obstaravatelia page

**Files:**
- Create: `src/uvo_gui/pages/procurers.py`
- Create: `tests/gui/test_procurers_page.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui/test_procurers_page.py
"""Tests for the Obstaravatelia page."""
from unittest.mock import AsyncMock, patch

import pytest
from nicegui.testing import User

MOCK_PROCURERS = {
    "items": [
        {"id": "p1", "nazov": "Ministerstvo vnútra SR", "ico": "00151866", "zakazky_count": 342, "total_value": 12400000},
        {"id": "p2", "nazov": "MDVaRR SR", "ico": "30416094", "zakazky_count": 187, "total_value": 8100000},
    ],
    "total": 2,
}


@pytest.mark.asyncio
async def test_procurers_page_shows_search_form(user: User) -> None:
    import uvo_gui.pages.procurers  # noqa: F401
    await user.open("/procurers")
    await user.should_contain("Hľadať obstarávateľa")
    await user.should_contain("Hľadať")


@pytest.mark.asyncio
async def test_procurers_page_shows_results(user: User) -> None:
    import uvo_gui.pages.procurers  # noqa: F401
    with patch(
        "uvo_gui.mcp_client.call_tool",
        new_callable=AsyncMock,
        return_value=MOCK_PROCURERS,
    ):
        await user.open("/procurers")
        user.find("Hľadať").click()
        await user.should_contain("Ministerstvo vnútra SR")
        await user.should_contain("MDVaRR SR")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/gui/test_procurers_page.py -v
```

Expected: `FAILED` — `ModuleNotFoundError` for `uvo_gui.pages.procurers`

- [ ] **Step 3: Create `src/uvo_gui/pages/procurers.py`**

```python
"""Obstaravatelia page — search for contracting authorities."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui

from uvo_gui import mcp_client
from uvo_gui.components.layout import layout

logger = logging.getLogger(__name__)


@dataclass
class ProcurersState:
    query: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    loading: bool = False
    error: str = ""

    async def search(self) -> None:
        self.loading = True
        self.error = ""
        procurers_view.refresh()
        try:
            arguments: dict[str, Any] = {"limit": 20, "offset": 0}
            if self.query:
                arguments["name_query"] = self.query
            data = await mcp_client.call_tool("find_procurer", arguments)
            self.results = data.get("items", [])
            self.total = data.get("total", 0)
        except Exception as exc:  # noqa: BLE001
            logger.error("Procurers search failed: %s", exc)
            self.error = f"Chyba pri vyhľadávaní: {exc}"
            self.results = []
            self.total = 0
        finally:
            self.loading = False
            procurers_view.refresh()


_state = ProcurersState()


@ui.refreshable
def procurers_view() -> None:
    if _state.loading:
        with ui.row().classes("justify-center py-6"):
            ui.spinner(size="md")
        return

    if _state.error:
        ui.label(_state.error).classes("text-red-600 text-sm py-2")
        return

    if not _state.results:
        return

    with ui.grid(columns=3).classes("w-full gap-4"):
        for item in _state.results:
            with ui.card().classes("w-full"):
                ui.label(item.get("nazov", "-")).classes("text-sm font-semibold text-slate-800 mb-2")
                ui.label(f"Zákazky: {item.get('zakazky_count', '-')}").classes(
                    "text-xs text-slate-500"
                )
                total = item.get("total_value")
                if total is not None:
                    ui.label(f"{total:,.0f} €".replace(",", " ")).classes(
                        "text-sm text-green-700 font-semibold"
                    )


@ui.page("/procurers")
async def procurers_page() -> None:
    with layout(current_path="/procurers"):
        with ui.column().classes("w-full p-4 gap-4"):
            ui.label("Obstaravatelia").classes("text-xl font-semibold text-slate-800")
            with ui.card().classes("w-full max-w-lg"):
                ui.label("Hľadať obstarávateľa").classes("text-sm font-semibold text-slate-700 mb-2")
                with ui.row().classes("w-full gap-2"):
                    ui.input(placeholder="Názov organizácie...").classes("flex-1").bind_value(
                        _state, "query"
                    )
                    ui.button("Hľadať", on_click=_state.search).classes(
                        "bg-blue-700 text-white"
                    ).props("no-caps")
            procurers_view()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/gui/test_procurers_page.py -v
```

Expected: both tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/uvo_gui/pages/procurers.py tests/gui/test_procurers_page.py
git commit -m "feat: add Obstaravatelia page with search and card grid"
```

---

## Task 4: Create Dodavatelia page

**Files:**
- Create: `src/uvo_gui/pages/suppliers.py`
- Create: `tests/gui/test_suppliers_page.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui/test_suppliers_page.py
"""Tests for the Dodavatelia page."""
from unittest.mock import AsyncMock, patch

import pytest
from nicegui.testing import User

MOCK_SUPPLIERS = {
    "items": [
        {"id": "s1", "nazov": "ACME Stavby s.r.o.", "ico": "12345678", "zakazky_count": 24, "total_value": 2100000},
        {"id": "s2", "nazov": "IT Solutions a.s.", "ico": "87654321", "zakazky_count": 41, "total_value": 5600000},
    ],
    "total": 2,
}


@pytest.mark.asyncio
async def test_suppliers_page_shows_search_form(user: User) -> None:
    import uvo_gui.pages.suppliers  # noqa: F401
    await user.open("/suppliers")
    await user.should_contain("Hľadať dodávateľa")
    await user.should_contain("Hľadať")


@pytest.mark.asyncio
async def test_suppliers_page_shows_results(user: User) -> None:
    import uvo_gui.pages.suppliers  # noqa: F401
    with patch(
        "uvo_gui.mcp_client.call_tool",
        new_callable=AsyncMock,
        return_value=MOCK_SUPPLIERS,
    ):
        await user.open("/suppliers")
        user.find("Hľadať").click()
        await user.should_contain("ACME Stavby s.r.o.")
        await user.should_contain("IČO: 12345678")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/gui/test_suppliers_page.py -v
```

Expected: `FAILED` — `ModuleNotFoundError` for `uvo_gui.pages.suppliers`

- [ ] **Step 3: Create `src/uvo_gui/pages/suppliers.py`**

```python
"""Dodavatelia page — search for suppliers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui

from uvo_gui import mcp_client
from uvo_gui.components.layout import layout

logger = logging.getLogger(__name__)


@dataclass
class SuppliersState:
    query: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    loading: bool = False
    error: str = ""

    async def search(self) -> None:
        self.loading = True
        self.error = ""
        suppliers_view.refresh()
        try:
            arguments: dict[str, Any] = {"limit": 20, "offset": 0}
            if self.query:
                # query could be a name or ICO — try name_query first; if numeric treat as ico
                if self.query.isdigit():
                    arguments["ico"] = self.query
                else:
                    arguments["name_query"] = self.query
            data = await mcp_client.call_tool("find_supplier", arguments)
            self.results = data.get("items", [])
            self.total = data.get("total", 0)
        except Exception as exc:  # noqa: BLE001
            logger.error("Suppliers search failed: %s", exc)
            self.error = f"Chyba pri vyhľadávaní: {exc}"
            self.results = []
            self.total = 0
        finally:
            self.loading = False
            suppliers_view.refresh()


_state = SuppliersState()


@ui.refreshable
def suppliers_view() -> None:
    if _state.loading:
        with ui.row().classes("justify-center py-6"):
            ui.spinner(size="md")
        return

    if _state.error:
        ui.label(_state.error).classes("text-red-600 text-sm py-2")
        return

    if not _state.results:
        return

    with ui.grid(columns=3).classes("w-full gap-4"):
        for item in _state.results:
            with ui.card().classes("w-full"):
                ui.label(item.get("nazov", "-")).classes("text-sm font-semibold text-slate-800 mb-1")
                ui.label(f"IČO: {item.get('ico', '-')}").classes("text-xs text-slate-400 mb-2")
                ui.label(f"Zákazky: {item.get('zakazky_count', '-')}").classes(
                    "text-xs text-slate-500"
                )
                total = item.get("total_value")
                if total is not None:
                    ui.label(f"{total:,.0f} €".replace(",", " ")).classes(
                        "text-sm text-green-700 font-semibold"
                    )


@ui.page("/suppliers")
async def suppliers_page() -> None:
    with layout(current_path="/suppliers"):
        with ui.column().classes("w-full p-4 gap-4"):
            ui.label("Dodavatelia").classes("text-xl font-semibold text-slate-800")
            with ui.card().classes("w-full max-w-lg"):
                ui.label("Hľadať dodávateľa").classes("text-sm font-semibold text-slate-700 mb-2")
                with ui.row().classes("w-full gap-2"):
                    ui.input(placeholder="Názov alebo IČO...").classes("flex-1").bind_value(
                        _state, "query"
                    )
                    ui.button("Hľadať", on_click=_state.search).classes(
                        "bg-blue-700 text-white"
                    ).props("no-caps")
            suppliers_view()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/gui/test_suppliers_page.py -v
```

Expected: both tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/uvo_gui/pages/suppliers.py tests/gui/test_suppliers_page.py
git commit -m "feat: add Dodavatelia page with search and card grid"
```

---

## Task 5: Create About page

**Files:**
- Create: `src/uvo_gui/pages/about.py`
- Create: `tests/gui/test_about_page.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/gui/test_about_page.py
"""Tests for the O aplikácii page."""
import pytest
from nicegui.testing import User


@pytest.mark.asyncio
async def test_about_page_renders_content(user: User) -> None:
    import uvo_gui.pages.about  # noqa: F401
    await user.open("/about")
    await user.should_contain("O aplikácii UVO Search")
    await user.should_contain("uvo.gov.sk")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/gui/test_about_page.py -v
```

Expected: `FAILED` — `ModuleNotFoundError` for `uvo_gui.pages.about`

- [ ] **Step 3: Create `src/uvo_gui/pages/about.py`**

```python
"""O aplikácii page — minimal description and data source attribution."""

from nicegui import ui

from uvo_gui.components.layout import layout


@ui.page("/about")
async def about_page() -> None:
    with layout(current_path="/about"):
        with ui.column().classes("w-full p-4 max-w-xl gap-3"):
            ui.label("O aplikácii UVO Search").classes("text-xl font-semibold text-slate-800")
            ui.label(
                "Aplikácia na prehliadanie dát z Vestníka verejného obstarávania SR. "
                "Dáta pochádzajú z portálu UVO a európskeho registra TED."
            ).classes("text-sm text-slate-600 leading-relaxed")
            ui.label("Zdroje dát: uvo.gov.sk · ted.europa.eu").classes("text-xs text-slate-400")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/gui/test_about_page.py -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/uvo_gui/pages/about.py tests/gui/test_about_page.py
git commit -m "feat: add O aplikácii page"
```

---

## Task 6: Wire up app.py and remove old components

**Files:**
- Modify: `src/uvo_gui/app.py`
- Delete: `src/uvo_gui/components/nav_header.py`
- Delete: `src/uvo_gui/components/detail_dialog.py`

- [ ] **Step 1: Update `src/uvo_gui/app.py`**

Replace the entire file with:

```python
"""NiceGUI application setup."""

from nicegui import ui

# Import pages to register @ui.page decorators
import uvo_gui.pages.about  # noqa: F401
import uvo_gui.pages.procurers  # noqa: F401
import uvo_gui.pages.search  # noqa: F401
import uvo_gui.pages.suppliers  # noqa: F401
from uvo_gui.config import GuiSettings

settings = GuiSettings()


def start() -> None:
    """Start the NiceGUI application server."""
    ui.run(
        title="UVO Search",
        storage_secret=settings.storage_secret,
        host=settings.gui_host,
        port=settings.gui_port,
    )
```

- [ ] **Step 2: Delete old components**

```bash
rm src/uvo_gui/components/nav_header.py
rm src/uvo_gui/components/detail_dialog.py
```

- [ ] **Step 3: Run full test suite to verify nothing is broken**

```bash
pytest tests/gui/ -v
```

Expected: all tests `PASSED`, no import errors

- [ ] **Step 4: Commit**

```bash
git add src/uvo_gui/app.py
git rm src/uvo_gui/components/nav_header.py src/uvo_gui/components/detail_dialog.py
git commit -m "feat: wire up all pages in app.py, remove old nav_header and detail_dialog"
```

---

## Task 7: Add .superpowers to .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Check current .gitignore**

```bash
grep -n "superpowers" .gitignore || echo "not present"
```

- [ ] **Step 2: Add entry if missing**

If not present, add to `.gitignore`:

```
.superpowers/
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .superpowers/ brainstorm artifacts"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Quasar layout shell (`ui.left_drawer`, `ui.header`, `ui.page_container`) | Task 1 |
| Light theme, white sidebar, blue accents | Task 1 (CSS classes) |
| Active nav item highlighted | Task 1 (`current_path` param) |
| Search page: split panel with left list + right detail | Task 2 |
| Search: selected row highlighted with blue border | Task 2 (`list_view`) |
| Detail panel: info grid (2×2 cards) | Task 2 (`detail_view`) |
| Detail panel: supplier list with IČO + badge | Task 2 (`detail_view`) |
| Obstaravatelia: search + card grid | Task 3 |
| Dodavatelia: search by name or IČO + card grid | Task 4 |
| About: minimal text + data source attribution | Task 5 |
| Register all 4 routes in app.py | Task 6 |
| Remove nav_header.py + detail_dialog.py | Task 6 |
| .superpowers/ in .gitignore | Task 7 |

**Placeholder scan:** None found — all steps have concrete code.

**Type consistency:** `_state.selected` is `dict | None` throughout. `list_view`, `detail_view`, `procurers_view`, `suppliers_view` are all `@ui.refreshable` functions called consistently by their respective state objects.
