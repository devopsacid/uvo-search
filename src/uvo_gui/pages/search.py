"""Search page — editorial record archive with large split detail view."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from nicegui import ui

from uvo_gui import mcp_client
from uvo_gui.components.layout import layout
from uvo_gui.components.search_box import search_box

logger = logging.getLogger(__name__)


# ── formatting helpers ────────────────────────────────────────────────────────
def _fmt_value(v: Any, currency: str = "EUR") -> tuple[str, bool]:
    """Return (display, is_none)."""
    if v is None or v == "":
        return ("—", True)
    try:
        n = float(v)
        symbol = "€" if currency in ("EUR", "", None) else currency
        return (f"{n:,.0f} {symbol}".replace(",", " "), False)
    except (TypeError, ValueError):
        return (str(v), False)


def _fmt_date(v: Any) -> str:
    if not v:
        return "—"
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y · %m · %d")
    s = str(v)
    # Accept "YYYY-MM-DD" or ISO timestamps
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y · %m · %d")
    except ValueError:
        return s


def _fmt_date_compact(v: Any) -> str:
    if not v:
        return "—"
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y-%m-%d")
    return str(v)[:10] or "—"


# ── state ─────────────────────────────────────────────────────────────────────
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
        raw = e.args if isinstance(e.args, dict) else (e.args[0] if e.args else {})
        pag = raw.get("pagination", raw) if isinstance(raw, dict) else {}
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

    def clear_selection(self) -> None:
        self.selected = None
        view.refresh()


_state = SearchState()


# ── detail panel ──────────────────────────────────────────────────────────────
def _render_detail_empty() -> None:
    with ui.column().classes("w-full h-full items-start justify-center").style(
        "padding: 64px 56px;"
    ):
        ui.html('<div class="uvo-detail-kicker">Záznam &nbsp;<span class="bar"></span></div>').style(
            "width: 100%; margin-bottom: 28px;"
        )
        ui.html(
            '<div class="uvo-detail-empty">'
            'Vyberte zákazku zo zoznamu,<br>aby sa zobrazil úplný záznam.'
            '<div class="hint">Kliknite na ľubovoľný riadok</div>'
            '</div>'
        )


def _render_detail(item: dict[str, Any]) -> None:
    title = item.get("title") or "—"
    description = item.get("description") or ""
    procurer = item.get("procurer") or {}
    procurer_name = procurer.get("name") or "—"
    procurer_ico = procurer.get("ico")
    procurer_addr = (procurer.get("address") or {})

    final_value = item.get("final_value")
    estimated_value = item.get("estimated_value")
    currency = item.get("currency") or "EUR"
    pub_date = item.get("publication_date")
    award_date = item.get("award_date")
    deadline_date = item.get("deadline_date")
    procedure = item.get("procedure_type") or "—"
    cpv = item.get("cpv_code") or "—"
    cpv_extra = item.get("cpv_codes_additional") or []
    status = item.get("status") or "unknown"
    source = (item.get("source") or "?").upper()
    source_id = item.get("source_id") or item.get("_id", "—")
    awards = item.get("awards") or []

    val_str, val_none = _fmt_value(final_value, currency)
    est_str, _ = _fmt_value(estimated_value, currency)

    with ui.column().classes("w-full h-full").style(
        "padding: 36px 52px 40px; overflow-y: auto; gap: 0;"
    ):
        # Kicker row + close
        with ui.row().classes("w-full items-center no-wrap").style("margin-bottom: 24px;"):
            ui.html(
                f'<div class="uvo-detail-kicker">'
                f'  Záznam &nbsp;'
                f'  <span class="mono" style="color: var(--ink-3); letter-spacing: 0.1em;">'
                f'    {source} · {source_id}'
                f'  </span>'
                f'  <span class="bar"></span>'
                f'</div>'
            ).style("flex: 1;")
            ui.button("×", on_click=_state.clear_selection).props("flat").classes("uvo-close")

        # Title
        ui.html(f'<h1 class="uvo-detail-title">{_escape(title)}</h1>').style(
            "margin: 0 0 10px;"
        )

        # Procurer (italic secondary line)
        ui.html(
            f'<div class="uvo-detail-procurer">'
            f'{_escape(procurer_name)}'
            f'</div>'
        ).style("margin-bottom: 20px;")

        # Status / source pills
        with ui.row().classes("items-center gap-2").style("margin-bottom: 28px;"):
            status_label = {
                "awarded": "Zazmluvnené",
                "announced": "Vyhlásené",
                "cancelled": "Zrušené",
            }.get(status, status.capitalize())
            ui.html(f'<span class="uvo-pill accent">● {status_label}</span>')
            ui.html(f'<span class="uvo-pill">Zdroj · {source}</span>')
            ui.html(f'<span class="uvo-pill">CPV · {cpv}</span>')

        # Hero value
        with ui.row().classes("w-full items-end no-wrap").style(
            "border-top: 1px solid var(--rule); padding-top: 22px; margin-bottom: 28px; gap: 48px;"
        ):
            with ui.column().classes("gap-1"):
                ui.html('<div class="uvo-detail-section-label">Konečná hodnota</div>')
                none_cls = " none" if val_none else ""
                parts = val_str.rsplit(" ", 1)
                if len(parts) == 2:
                    num, unit = parts
                    ui.html(
                        f'<div class="uvo-detail-value big{none_cls}">{_escape(num)}'
                        f'<span class="unit">{_escape(unit)}</span></div>'
                    )
                else:
                    ui.html(f'<div class="uvo-detail-value big{none_cls}">{_escape(val_str)}</div>')
            with ui.column().classes("gap-1"):
                ui.html('<div class="uvo-detail-section-label">Odhad</div>')
                ui.html(f'<div class="uvo-detail-value">{_escape(est_str)}</div>')
            with ui.column().classes("gap-1"):
                ui.html('<div class="uvo-detail-section-label">Procedúra</div>')
                ui.html(f'<div class="uvo-detail-value">{_escape(str(procedure))}</div>')

        # Description (drop-cap paragraph)
        if description:
            ui.html('<div class="uvo-detail-section-label">Opis</div>').style(
                "margin-bottom: 8px;"
            )
            desc = _escape(description.strip())
            ui.html(f'<p class="uvo-detail-desc">{desc}</p>').style(
                "margin: 0 0 28px;"
            )

        # Metadata grid
        with ui.element("div").classes("uvo-metagrid w-full").style("margin-bottom: 28px;"):
            _meta_cell("Dátum zverejnenia", _fmt_date(pub_date))
            _meta_cell("Dátum pridelenia", _fmt_date(award_date))
            _meta_cell("Lehota na podanie", _fmt_date(deadline_date))
            _meta_cell(
                "Obstarávateľ",
                procurer_name,
                sub=(
                    f"IČO {procurer_ico}" if procurer_ico else None
                ),
            )
            city = procurer_addr.get("city")
            street = procurer_addr.get("street")
            addr_line = " · ".join(x for x in [street, city] if x) or "—"
            _meta_cell("Sídlo", addr_line)
            extra = ", ".join(cpv_extra[:3]) if cpv_extra else "—"
            _meta_cell("Doplnkové CPV", extra)

        # Awards
        ui.html('<div class="uvo-detail-section-label">Víťazné ponuky</div>').style(
            "margin-bottom: 10px;"
        )
        if awards:
            with ui.column().classes("w-full").style("gap: 0;"):
                for i, aw in enumerate(awards, start=1):
                    supplier = (aw.get("supplier") or {})
                    sname = supplier.get("name") or "—"
                    ico = supplier.get("ico")
                    aval_str, _ = _fmt_value(aw.get("value"), aw.get("currency") or currency)
                    sign = _fmt_date_compact(aw.get("signing_date"))
                    contract = aw.get("contract_number") or ""
                    meta_bits = []
                    if ico:
                        meta_bits.append(f"IČO {ico}")
                    if contract:
                        meta_bits.append(f"zml. {contract}")
                    if sign and sign != "—":
                        meta_bits.append(sign)
                    meta = " · ".join(meta_bits) or "—"
                    ui.html(
                        f'<div class="uvo-award-row">'
                        f'  <span class="idx">{i:02d}</span>'
                        f'  <div>'
                        f'    <div class="name">{_escape(sname)}</div>'
                        f'    <div class="meta">{_escape(meta)}</div>'
                        f'  </div>'
                        f'  <span class="val">{_escape(aval_str)}</span>'
                        f'</div>'
                    )
        else:
            ui.html(
                '<div class="uvo-detail-value" style="color: var(--ink-3); font-style: italic;">'
                'Žiadne záznamy o víťazoch.'
                '</div>'
            )


def _meta_cell(label: str, value: str, sub: str | None = None) -> None:
    sub_html = (
        f'<div class="mono" style="font-size:10px;color:var(--ink-3);margin-top:4px;">'
        f'{_escape(sub)}</div>'
        if sub
        else ""
    )
    ui.html(
        f'<div>'
        f'  <div class="uvo-detail-section-label">{_escape(label)}</div>'
        f'  <div class="uvo-detail-value" style="font-size:14px;">{_escape(value)}</div>'
        f'  {sub_html}'
        f'</div>'
    )


def _escape(s: Any) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ── main view ─────────────────────────────────────────────────────────────────
@ui.refreshable
def view() -> None:
    has_selection = _state.selected is not None

    with ui.row().classes("w-full no-wrap").style(
        "gap: 0; align-items: stretch; min-height: calc(100vh - 160px);"
    ):
        # Left: search + table
        left_flex = "flex: 1 1 0;" if has_selection else "flex: 1 1 100%;"
        with ui.column().classes("h-full").style(
            f"{left_flex} min-width: 520px; padding-right: 32px; gap: 18px;"
        ):
            # Editorial kicker above search
            with ui.row().classes("items-baseline no-wrap").style("gap: 14px;"):
                ui.html(
                    '<span class="mono" style="font-size:10px;letter-spacing:0.22em;'
                    'text-transform:uppercase;color:var(--ink-3);">Hľadať v archíve</span>'
                )
                ui.html(
                    f'<span class="mono" style="font-size:10px;color:var(--ink-3);">'
                    f'{_state.total:,}'.replace(",", " ") + ' záznamov</span>'
                )

            with ui.element("div").classes("uvo-search w-full"):
                search_box(
                    types=["notice", "procurer", "supplier"],
                    on_submit=_state.submit,
                    on_select=lambda item: _state.submit(item.get("label", "")),
                )
            if _state.error:
                ui.html(
                    f'<div style="border-left: 2px solid var(--accent); padding: 8px 14px;'
                    f' background: rgba(176,78,30,0.06); font-family: \'Fraunces\', serif;'
                    f' font-style: italic; color: var(--accent); font-size: 14px;">'
                    f'{_escape(_state.error)}</div>'
                )

            # Flatten for table
            flat_rows = []
            for r in _state.rows:
                proc = (r.get("procurer") or {}).get("name", "—")
                val_disp, val_none = _fmt_value(r.get("final_value"), r.get("currency") or "EUR")
                date_disp = _fmt_date_compact(r.get("publication_date"))
                flat_rows.append(
                    {
                        **r,
                        "_procurer_name": proc,
                        "_value_disp": val_disp,
                        "_value_none": val_none,
                        "_date_disp": date_disp,
                    }
                )

            columns = [
                {"name": "title", "label": "Názov", "field": "title",
                 "sortable": True, "align": "left"},
                {"name": "_procurer_name", "label": "Obstarávateľ",
                 "field": "_procurer_name", "sortable": False, "align": "left"},
                {"name": "final_value", "label": "Hodnota", "field": "_value_disp",
                 "sortable": True, "align": "right"},
                {"name": "publication_date", "label": "Dátum",
                 "field": "_date_disp", "sortable": True, "align": "left"},
            ]
            table = (
                ui.table(
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
                )
                .props("flat")
                .classes("uvo-table w-full")
            )
            # Custom cell rendering via Quasar slots for editorial typography
            table.add_slot(
                "body-cell-title",
                '<q-td :props="props"><div class="uvo-cell-title">{{ props.value }}</div></q-td>',
            )
            table.add_slot(
                "body-cell-_procurer_name",
                '<q-td :props="props"><div class="uvo-cell-procurer">{{ props.value }}</div></q-td>',
            )
            table.add_slot(
                "body-cell-final_value",
                '<q-td :props="props" class="text-right">'
                '<span :class="props.row._value_none ? \'uvo-cell-value none\' : \'uvo-cell-value\'">'
                '{{ props.value }}</span></q-td>',
            )
            table.add_slot(
                "body-cell-publication_date",
                '<q-td :props="props"><span class="uvo-cell-mono">{{ props.value }}</span></q-td>',
            )

            table.on("request", lambda e: asyncio.ensure_future(_state.on_pagination(e)))
            table.on(
                "rowClick",
                lambda e: _state.select(e.args[1] if len(e.args) > 1 else {}),
            )

            if _state.loading:
                ui.spinner(size="md").classes("self-center")

        # Right: detail panel
        detail_style = (
            "flex: 1 1 0; min-width: 560px;"
            if has_selection
            else "flex: 0 0 380px; opacity: 0.7;"
        )
        with ui.column().classes("uvo-detail h-full").style(detail_style):
            if _state.selected is None:
                _render_detail_empty()
            else:
                _render_detail(_state.selected)


@ui.page("/")
async def search_page() -> None:
    with layout(current_path="/"):
        view()
        await _state.fetch()
