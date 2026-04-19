"""Reusable live-search input with autocomplete dropdown."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from nicegui import ui

from uvo_gui import mcp_client

logger = logging.getLogger(__name__)

_DEBOUNCE_SEC = 0.3
_pending_tasks: list[asyncio.Task] = []


async def _flush_for_tests() -> None:
    while _pending_tasks:
        t = _pending_tasks.pop(0)
        try:
            await t
        except Exception:
            pass


def search_box(
    *,
    placeholder: str = '🔍 Hľadať… (použite * pre začiatok slova, "..." pre presnú frázu)',
    types: list[str] | None = None,
    on_submit: Callable[[str], Awaitable[None]] | None = None,
    on_select: Callable[[dict], Awaitable[None]] | None = None,
    debounce: float = _DEBOUNCE_SEC,
) -> None:
    """Render an input with a menu that lists live autocomplete results."""
    types = types or ["procurer", "supplier", "notice"]
    state = {"query": "", "task": None, "results": []}

    @ui.refreshable
    def dropdown() -> None:
        if not state["results"]:
            return
        with ui.card().classes("absolute z-50 w-full mt-1 p-0 shadow-lg bg-white"):
            for item in state["results"]:
                row = ui.row().classes(
                    "w-full p-2 hover:bg-slate-50 cursor-pointer items-center gap-2"
                )
                with row:
                    icon = {"procurer": "🏢", "supplier": "🤝", "notice": "📄"}.get(
                        item["type"], "•"
                    )
                    ui.label(icon).classes("text-sm")
                    with ui.column().classes("gap-0"):
                        ui.label(item["label"]).classes(
                            "text-sm font-semibold text-slate-800"
                        )
                        if item.get("sublabel"):
                            ui.label(item["sublabel"]).classes("text-xs text-slate-400")
                row.on("click", lambda i=item: asyncio.ensure_future(_handle_select(i)))

    async def _handle_select(item: dict) -> None:
        state["results"] = []
        dropdown.refresh()
        if on_select:
            await on_select(item)

    async def _fetch(q: str) -> None:
        try:
            data = await mcp_client.call_tool(
                "search_autocomplete", {"query": q, "types": types, "limit": 5}
            )
            state["results"] = data.get("results", [])
        except Exception as exc:
            logger.warning("autocomplete failed: %s", exc)
            state["results"] = []
        dropdown.refresh()

    async def _debounced_fetch(q: str) -> None:
        if debounce > 0:
            await asyncio.sleep(debounce)
        if q == state["query"]:
            await _fetch(q)

    def _on_change(e) -> None:
        val = getattr(e, "value", None)
        if val is None:
            val = ""
        state["query"] = val or ""
        if state["task"] and not state["task"].done():
            state["task"].cancel()
        if not state["query"].strip():
            state["results"] = []
            dropdown.refresh()
            return
        task = asyncio.ensure_future(_debounced_fetch(state["query"]))
        state["task"] = task
        _pending_tasks.append(task)

    async def _on_submit() -> None:
        if on_submit:
            await on_submit(state["query"])

    with ui.column().classes("w-full relative"):
        ui.input(placeholder=placeholder, on_change=lambda e: _on_change(e)).classes("w-full").on(
            "keydown.enter", lambda _: asyncio.ensure_future(_on_submit())
        )
        dropdown()
