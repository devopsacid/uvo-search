"""Shared navigation header component for all pages."""
from nicegui import ui


def nav_header() -> None:
    """Render the top navigation bar shared across all pages."""
    with ui.header().classes("bg-blue-800 text-white"):
        with ui.row().classes("w-full max-w-screen-xl mx-auto items-center"):
            ui.label("UVO Search").classes("text-xl font-bold cursor-pointer").on(
                "click", lambda: ui.navigate.to("/")
            )
            ui.space()
            with ui.row().classes("gap-4"):
                ui.link("Vyhladavanie", "/").classes("text-white")
                ui.link("Obstaravatelia", "/procurers").classes("text-white")
                ui.link("Dodavatelia", "/suppliers").classes("text-white")
                ui.link("O aplikacii", "/about").classes("text-white")
