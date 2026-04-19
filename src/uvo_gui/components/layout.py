"""Shared editorial layout shell — header + numbered sidebar."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime

from nicegui import ui

from uvo_gui.components.theme import apply_theme

NAV_ITEMS = [
    ("Vyhľadávanie",  "Records",      "/"),
    ("Obstaravatelia", "Authorities", "/procurers"),
    ("Dodavatelia",    "Suppliers",   "/suppliers"),
    ("Sieť",           "Network",     "/graph"),
    ("O aplikácii",    "Colophon",    "/about"),
]


@contextmanager
def layout(current_path: str = "/") -> Generator[None, None, None]:
    """Render the editorial app shell (header + sidebar + page container)."""
    apply_theme()

    with ui.header().props("elevated=false").classes("uvo-header"):
        with ui.row().classes("w-full items-center no-wrap px-6 h-full"):
            with ui.column().classes("gap-0"):
                ui.label("UVO Search").classes("uvo-wordmark")
                ui.label("Vestník verejného obstarávania — SK").classes("uvo-kicker")
            ui.element("div").classes("flex-1")
            ui.html(
                f'<span class="uvo-tally">EDITION · <b>{datetime.now():%Y.%m.%d}</b>'
                f' &nbsp;·&nbsp; VOL. <b>XVII</b></span>'
            )

    with ui.left_drawer(value=True).props("bordered=false width=220").classes("uvo-drawer"):
        ui.html('<div class="uvo-nav-label">Navigácia</div>')
        for idx, (label, en, path) in enumerate(NAV_ITEMS, start=1):
            active = "active" if current_path == path else ""
            node = ui.html(
                f'<div class="uvo-nav-item {active}">'
                f'  <span class="num">{idx:02d}</span>'
                f'  <span>{label}</span>'
                f'  <span class="num" style="margin-left:auto">{en}</span>'
                f'</div>'
            )
            node.on("click", lambda p=path: ui.navigate.to(p))
            node.style("cursor: pointer")

        ui.html(
            '<div class="uvo-drawer-footer">'
            '  Open archive · maxian.sk'
            '</div>'
        )

    with ui.column().classes("w-full h-full").style(
        "padding: 24px 40px 24px 32px; position: relative; z-index: 1;"
    ):
        yield
