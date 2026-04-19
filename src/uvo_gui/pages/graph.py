"""Relationship-network page with ego and CPV sub-tabs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from nicegui import ui

from uvo_gui import mcp_client
from uvo_gui.components.layout import layout
from uvo_gui.components.search_box import search_box

logger = logging.getLogger(__name__)


@dataclass
class GraphState:
    mode: str = "ego"
    ico: str = ""
    max_hops: int = 2
    cpv_code: str = ""
    year: int = field(default_factory=lambda: datetime.now(UTC).year - 1)
    payload: dict[str, Any] = field(default_factory=lambda: {"nodes": [], "edges": []})
    loading: bool = False
    error: str = ""

    async def load(self) -> None:
        self.loading = True
        self.error = ""
        view.refresh()
        try:
            if self.mode == "ego":
                if not self.ico:
                    self.payload = {"nodes": [], "edges": []}
                else:
                    self.payload = await mcp_client.call_tool(
                        "graph_ego_network",
                        {"ico": self.ico, "max_hops": self.max_hops},
                    )
            else:
                if not self.cpv_code:
                    self.payload = {"nodes": [], "edges": []}
                else:
                    self.payload = await mcp_client.call_tool(
                        "graph_cpv_network",
                        {"cpv_code": self.cpv_code, "year": self.year},
                    )
        except Exception as exc:
            logger.error("graph fetch failed: %s", exc)
            self.error = f"Chyba: {exc}"
            self.payload = {"nodes": [], "edges": []}
        finally:
            self.loading = False
            view.refresh()
            await self.render()

    async def render(self) -> None:
        js = f"renderGraph('graph-canvas', {json.dumps(self.payload)});"
        ui.run_javascript(js)


_state = GraphState()


async def _on_select_entity(item: dict) -> None:
    _state.ico = item.get("id", "")
    await _state.load()


def _set_mode(mode: str) -> None:
    _state.mode = mode
    _state.payload = {"nodes": [], "edges": []}
    view.refresh()


@ui.refreshable
def view() -> None:
    with ui.column().classes("w-full h-full gap-2"):
        ui.label("Sieť vzťahov").classes("text-xl font-semibold text-slate-800")
        with ui.tabs().classes("w-full") as tabs:
            ui.tab("ego", label="Ego-sieť")
            ui.tab("cpv", label="CPV-sieť")
        with ui.tab_panels(tabs, value="ego").classes("w-full"):
            with ui.tab_panel("ego"):
                with ui.row().classes("w-full gap-2 items-end"):
                    with ui.column().classes("flex-1"):
                        search_box(
                            types=["procurer", "supplier"],
                            on_submit=lambda q: _state.load(),
                            on_select=_on_select_entity,
                        )
                    ui.number(label="Max. skokov", value=_state.max_hops, min=1, max=3).bind_value(
                        _state, "max_hops"
                    )
                    ui.button("Načítať", on_click=_state.load).props("no-caps").classes(
                        "bg-blue-700 text-white"
                    )
            with ui.tab_panel("cpv"):
                with ui.row().classes("w-full gap-2 items-end"):
                    ui.input(label="CPV kód", placeholder="napr. 48000000").classes(
                        "flex-1"
                    ).bind_value(_state, "cpv_code")
                    ui.number(label="Rok", value=_state.year).bind_value(_state, "year")
                    ui.button("Načítať", on_click=_state.load).props("no-caps").classes(
                        "bg-blue-700 text-white"
                    )

        if _state.error:
            ui.label(_state.error).classes("text-red-600 text-sm")
        if _state.loading:
            ui.spinner(size="md")
        ui.html(
            '<div id="graph-canvas" style="width:100%;height:600px;'
            'border:1px solid #e2e8f0;border-radius:6px;"></div>'
        )


@ui.page("/graph")
async def graph_page() -> None:
    ui.add_head_html(
        '<script src="https://unpkg.com/vis-network@9/standalone/umd/vis-network.min.js"></script>'
    )
    ui.add_body_html('<script src="/static/graph_render.js"></script>')
    with layout(current_path="/graph"):
        view()
