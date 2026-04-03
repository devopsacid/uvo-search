"""Main search page — lists completed procurements with filtering and pagination."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui

from uvo_gui.components.nav_header import nav_header
from uvo_gui import mcp_client

logger = logging.getLogger(__name__)

COLUMNS = [
    {"name": "id", "label": "ID", "field": "id", "align": "left"},
    {"name": "nazov", "label": "Nazov", "field": "nazov", "align": "left"},
    {"name": "obstaravatel_nazov", "label": "Obstaravatel", "field": "obstaravatel_nazov", "align": "left"},
    {"name": "konecna_hodnota", "label": "Hodnota (EUR)", "field": "konecna_hodnota", "align": "right"},
    {"name": "datum_zverejnenia", "label": "Datum", "field": "datum_zverejnenia", "align": "left"},
    {"name": "cpv_kod", "label": "CPV", "field": "cpv_kod", "align": "left"},
    {"name": "stav", "label": "Stav", "field": "stav", "align": "left"},
]


@dataclass
class SearchState:
    """Holds the current search parameters, results, and pagination state."""

    query: str = ""
    date_from: str = ""
    date_to: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    loading: bool = False
    error: str = ""

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def total_pages(self) -> int:
        if self.total == 0:
            return 1
        return max(1, -(-self.total // self.per_page))  # ceiling division

    async def search(self) -> None:
        """Reset to page 1 and fetch results."""
        self.page = 1
        await self._fetch()

    async def goto_page(self, page: int) -> None:
        """Navigate to a specific page and fetch results."""
        self.page = max(1, min(page, self.total_pages))
        await self._fetch()

    async def _fetch(self) -> None:
        """Fetch results from the MCP server and refresh the view."""
        self.loading = True
        self.error = ""
        results_view.refresh()
        try:
            arguments: dict[str, Any] = {
                "limit": self.per_page,
                "offset": self.offset,
            }
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
            self.error = f"Chyba pri vyhladavani: {exc}"
            self.results = []
            self.total = 0
        finally:
            self.loading = False
            results_view.refresh()


_state = SearchState()


@ui.refreshable
def results_view() -> None:
    """Refreshable results area — shows spinner, error, empty state, or table."""
    if _state.loading:
        with ui.row().classes("justify-center w-full py-8"):
            ui.spinner(size="lg")
        return

    if _state.error:
        ui.label(_state.error).classes("text-red-600 py-4")
        return

    if not _state.results:
        ui.label("Zadajte hladany vyraz a stlacte Hladat.").classes("text-gray-500 py-4")
        return

    # Results table
    table = ui.table(columns=COLUMNS, rows=_state.results, row_key="id").classes("w-full")
    table.on("rowClick", lambda e: show_detail_dialog(e.args[1]))

    # Pagination controls
    with ui.row().classes("items-center gap-4 py-2"):
        ui.button(
            "Predchadzajuca",
            on_click=lambda: ui.timer(0, lambda: _state.goto_page(_state.page - 1), once=True),
        ).props("flat").set_enabled(_state.page > 1)

        ui.label(f"Strana {_state.page} z {_state.total_pages}").classes("text-sm")

        ui.button(
            "Nasledujuca",
            on_click=lambda: ui.timer(0, lambda: _state.goto_page(_state.page + 1), once=True),
        ).props("flat").set_enabled(_state.page < _state.total_pages)

    ui.label(f"Celkovy pocet: {_state.total}").classes("text-sm text-gray-500")


def show_detail_dialog(procurement: dict) -> None:
    """Import lazily to avoid circular imports."""
    from uvo_gui.components.detail_dialog import show_detail_dialog as _show
    _show(procurement)


@ui.page("/")
async def search_page() -> None:
    """Main search page with filter form and paginated results table."""
    nav_header()

    with ui.column().classes("w-full max-w-screen-xl mx-auto p-4 gap-4"):
        ui.label("Vyhladavanie zakaziek").classes("text-2xl font-bold")

        # Search form
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full flex-wrap gap-4 items-end"):
                with ui.column().classes("flex-1 min-w-48"):
                    ui.label("Hladany vyraz").classes("text-sm font-medium")
                    ui.input(placeholder="Napr. stavebne prace...").classes("w-full").bind_value(
                        _state, "query"
                    )

                with ui.column().classes("min-w-36"):
                    ui.label("Datum od").classes("text-sm font-medium")
                    ui.input(placeholder="YYYY-MM-DD").classes("w-full").bind_value(
                        _state, "date_from"
                    )

                with ui.column().classes("min-w-36"):
                    ui.label("Datum do").classes("text-sm font-medium")
                    ui.input(placeholder="YYYY-MM-DD").classes("w-full").bind_value(
                        _state, "date_to"
                    )

                ui.button("Hladat", on_click=_state.search).classes(
                    "bg-blue-700 text-white"
                )

        results_view()
