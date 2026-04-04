"""Search page — split panel: left result list, right detail view."""

from __future__ import annotations

import asyncio
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
            with ui.card().classes(card_classes):
                ui.label(item.get("nazov", "-")).classes(
                    "text-sm font-semibold " + ("text-blue-700" if selected else "text-slate-800")
                ).on("click", lambda i=item: _state.select(i))
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
            on_click=lambda: asyncio.ensure_future(_state.goto_page(_state.page - 1)),
        ).props("flat no-caps").classes("text-xs").set_enabled(_state.page > 1)
        ui.label(f"{_state.page} / {_state.total_pages}").classes("text-xs text-slate-500")
        ui.button(
            "Ďalšia →",
            on_click=lambda: asyncio.ensure_future(_state.goto_page(_state.page + 1)),
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
                extra = (
                    "text-green-700 font-bold text-base"
                    if key == "konecna_hodnota"
                    else "text-sm font-semibold text-slate-800"
                )
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
        with ui.row().classes("w-full h-full gap-4"):
            with ui.column().classes("w-72 flex-shrink-0 h-full"):
                list_view()
            with ui.column().classes("flex-1 h-full"):
                with ui.card().classes("w-full h-full p-4"):
                    detail_view()
