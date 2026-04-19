"""Search page — sortable/paginated notices table + detail panel."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui

from uvo_gui import mcp_client
from uvo_gui.components.layout import layout
from uvo_gui.components.search_box import search_box

logger = logging.getLogger(__name__)


@dataclass
class SearchState:
    query: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    sort_field: str = "publication_date"
    sort_desc: bool = True
    loading: bool = False
    error: str = ""
    selected: dict[str, Any] | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    async def submit(self, q: str) -> None:
        self.query = q
        self.page = 1
        await self.fetch()

    async def on_pagination(self, e) -> None:
        pag = e.args if isinstance(e.args, dict) else (e.args[0] if e.args else {})
        self.page = pag.get("page", 1)
        self.per_page = pag.get("rowsPerPage", 20)
        self.sort_field = pag.get("sortBy") or self.sort_field
        self.sort_desc = bool(pag.get("descending", True))
        await self.fetch()

    async def fetch(self) -> None:
        self.loading = True
        self.error = ""
        view.refresh()
        try:
            args: dict[str, Any] = {"limit": self.per_page, "offset": self.offset}
            if self.query:
                args["text_query"] = self.query
            data = await mcp_client.call_tool("search_completed_procurements", args)
            self.rows = data.get("items", [])
            self.total = data.get("total", 0)
        except Exception as exc:
            logger.error("search failed: %s", exc)
            self.error = f"Chyba pri vyhľadávaní: {exc}"
            self.rows = []
            self.total = 0
        finally:
            self.loading = False
            view.refresh()

    def select(self, row: dict) -> None:
        self.selected = row
        view.refresh()


_state = SearchState()


@ui.refreshable
def view() -> None:
    with ui.row().classes("w-full h-full gap-4"):
        with ui.column().classes("flex-1 h-full gap-2"):
            search_box(
                types=["notice", "procurer", "supplier"],
                on_submit=_state.submit,
                on_select=lambda item: _state.submit(item.get("label", "")),
            )
            if _state.error:
                ui.label(_state.error).classes("text-red-600 text-sm")

            # Flatten procurer name into each row so the field can be a plain string key.
            flat_rows = [
                {**r, "_procurer_name": (r.get("procurer") or {}).get("name", "-")}
                for r in _state.rows
            ]
            columns = [
                {"name": "title", "label": "Názov", "field": "title",
                 "sortable": True, "align": "left"},
                {"name": "_procurer_name", "label": "Obstarávateľ",
                 "field": "_procurer_name",
                 "sortable": False, "align": "left"},
                {"name": "final_value", "label": "Hodnota €", "field": "final_value",
                 "sortable": True, "align": "right"},
                {"name": "publication_date", "label": "Dátum",
                 "field": "publication_date", "sortable": True, "align": "left"},
            ]
            table = ui.table(
                columns=columns,
                rows=flat_rows,
                row_key="_id",
                pagination={
                    "rowsPerPage": _state.per_page,
                    "page": _state.page,
                    "rowsNumber": _state.total,
                    "sortBy": _state.sort_field,
                    "descending": _state.sort_desc,
                },
            ).props("flat bordered").classes("w-full")
            table.on("request", lambda e: asyncio.ensure_future(_state.on_pagination(e)))
            table.on("rowClick", lambda e: _state.select(e.args[1] if len(e.args) > 1 else {}))

            if _state.loading:
                ui.spinner(size="md").classes("self-center")

        with ui.column().classes("w-96 h-full"):
            with ui.card().classes("w-full h-full p-4"):
                if _state.selected is None:
                    ui.label("Vyberte zákazku zo zoznamu").classes(
                        "text-sm text-slate-400"
                    )
                else:
                    item = _state.selected
                    ui.label(item.get("title", "-")).classes(
                        "text-lg font-semibold text-slate-800 mb-2"
                    )
                    ui.label((item.get("procurer") or {}).get("name", "-")).classes(
                        "text-sm text-slate-500 mb-1"
                    )
                    ui.label(f"{item.get('final_value', '-')} €").classes(
                        "text-base text-green-700 font-bold"
                    )
                    ui.label(str(item.get("publication_date", "-"))).classes(
                        "text-sm text-slate-500"
                    )


@ui.page("/")
async def search_page() -> None:
    with layout(current_path="/"):
        view()
        await _state.fetch()
