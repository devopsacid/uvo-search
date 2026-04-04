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

    # ui.page_container does not exist in NiceGUI 3.9; use column as content wrapper
    with ui.column().classes("w-full h-full p-4"):
        yield
