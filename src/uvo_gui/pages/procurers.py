"""Procurers page — search + paginated table of contracting authorities."""

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
class ProcurersState:
    query: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    sort_field: str = "name"
    sort_desc: bool = False
    loading: bool = False
    error: str = ""

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
        self.sort_desc = bool(pag.get("descending", False))
        await self.fetch()

    async def fetch(self) -> None:
        self.loading = True
        self.error = ""
        view.refresh()
        try:
            allowed = {"name", "contract_count", "total_value"}
            args: dict[str, Any] = {
                "limit": self.per_page,
                "offset": self.offset,
                "sort_by": self.sort_field if self.sort_field in allowed else "name",
            }
            if self.query:
                args["name_query"] = self.query
            data = await mcp_client.call_tool("find_procurer", args)
            self.rows = data.get("items", [])
            self.total = data.get("total", 0)
        except Exception as exc:
            logger.error("procurers fetch failed: %s", exc)
            self.error = f"Chyba pri vyhľadávaní: {exc}"
            self.rows = []
            self.total = 0
        finally:
            self.loading = False
            view.refresh()


_state = ProcurersState()


@ui.refreshable
def view() -> None:
    with ui.column().classes("w-full gap-4"):
        ui.label("Obstaravatelia").classes("text-xl font-semibold text-slate-800")
        search_box(
            types=["procurer"],
            on_submit=_state.submit,
            on_select=lambda i: _state.submit(i.get("label", "")),
        )
        if _state.error:
            ui.label(_state.error).classes("text-red-600 text-sm")

        columns = [
            {"name": "name", "label": "Názov", "field": "name",
             "sortable": True, "align": "left"},
            {"name": "ico", "label": "IČO", "field": "ico",
             "sortable": False, "align": "left"},
            {"name": "contract_count", "label": "Počet zákaziek",
             "field": "contract_count", "sortable": True, "align": "right"},
            {"name": "total_value", "label": "Celková hodnota €",
             "field": "total_value", "sortable": True, "align": "right"},
        ]
        table = ui.table(
            columns=columns,
            rows=_state.rows,
            row_key="ico",
            pagination={
                "rowsPerPage": _state.per_page,
                "page": _state.page,
                "rowsNumber": _state.total,
                "sortBy": _state.sort_field,
                "descending": _state.sort_desc,
            },
        ).props("flat bordered").classes("w-full")
        table.on("request", lambda e: asyncio.ensure_future(_state.on_pagination(e)))

        if _state.loading:
            ui.spinner(size="md").classes("self-center")


@ui.page("/procurers")
async def procurers_page() -> None:
    with layout(current_path="/procurers"):
        view()
        await _state.fetch()
