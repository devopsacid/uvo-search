"""Minimal NiceGUI app for testing the layout component."""

from nicegui import ui

from uvo_gui.components.layout import layout


@ui.page("/test-layout")
async def test_layout_page() -> None:
    with layout(current_path="/test-layout"):
        ui.label("page content")


ui.run(storage_secret="test-secret")
