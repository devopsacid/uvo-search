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
                # if purely numeric treat as ICO, otherwise name search
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
