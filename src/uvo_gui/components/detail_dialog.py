"""Procurement detail dialog component."""

from nicegui import ui


def show_detail_dialog(procurement: dict) -> None:
    """Open a modal dialog displaying full detail for a single procurement."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl"):
        ui.label(procurement.get("nazov", "Detail")).classes("text-xl font-bold")
        ui.separator()
        with ui.grid(columns=2).classes("w-full gap-2"):
            ui.label("Obstaravatel:").classes("font-semibold")
            ui.label(str(procurement.get("obstaravatel_nazov", "-")))
            ui.label("Hodnota:").classes("font-semibold")
            ui.label(f"{procurement.get('konecna_hodnota', '-')} EUR")
            ui.label("Datum:").classes("font-semibold")
            ui.label(str(procurement.get("datum_zverejnenia", "-")))
            ui.label("CPV kod:").classes("font-semibold")
            ui.label(str(procurement.get("cpv_kod", "-")))
            ui.label("Stav:").classes("font-semibold")
            ui.label(str(procurement.get("stav", "-")))
        if procurement.get("dodavatelia"):
            ui.separator()
            ui.label("Dodavatelia").classes("font-semibold mt-2")
            for s in procurement["dodavatelia"]:
                with ui.card().classes("w-full"):
                    ui.label(s.get("nazov", "-"))
                    ui.label(f"ICO: {s.get('ico', '-')}").classes("text-sm text-gray-500")
        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Zavriet", on_click=dialog.close)
    dialog.open()
