"""O aplikácii page — minimal description and data source attribution."""

from nicegui import ui

from uvo_gui.components.layout import layout


@ui.page("/about")
async def about_page() -> None:
    with layout(current_path="/about"):
        with ui.column().classes("w-full p-4 max-w-xl gap-3"):
            ui.label("O aplikácii UVO Search").classes("text-xl font-semibold text-slate-800")
            ui.label(
                "Aplikácia na prehliadanie dát z Vestníka verejného obstarávania SR. "
                "Dáta pochádzajú z portálu UVO a európskeho registra TED."
            ).classes("text-sm text-slate-600 leading-relaxed")
            ui.label("Zdroje dát: uvo.gov.sk · ted.europa.eu").classes("text-xs text-slate-400")
