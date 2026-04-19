"""Global editorial theme — fonts, CSS variables, Quasar overrides.

Injected once via ``apply_theme()`` called from the layout. Aesthetic direction
is an archival / editorial feel: warm paper background, deep ink, a single
burnt-sienna accent, serif display for record titles, grotesque sans for UI,
JetBrains Mono for tabular figures.
"""

from __future__ import annotations

from nicegui import ui

_APPLIED = False

_HEAD_HTML = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..700;1,9..144,300..600&family=Manrope:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root {
  --paper:      #F4EFE3;
  --paper-2:    #EDE6D4;
  --paper-3:    #E4DCC5;
  --rule:       #D2C9AE;
  --rule-soft:  #E4DCC5;
  --ink:        #16181D;
  --ink-2:      #3A3A44;
  --ink-3:      #6F6A5E;
  --accent:     #B04E1E;
  --accent-2:   #7B6B3D;
  --muted-bg:   rgba(22, 24, 29, 0.04);
  --selected-bg: rgba(176, 78, 30, 0.06);
  --shadow-1:   0 1px 0 var(--rule-soft);
}

html, body, .q-page, .q-layout, .nicegui-content {
  background: var(--paper) !important;
  color: var(--ink);
  font-family: 'Manrope', ui-sans-serif, system-ui, sans-serif;
  font-feature-settings: 'ss01', 'cv11';
  letter-spacing: -0.005em;
}

/* Subtle paper grain */
body::before {
  content: "";
  position: fixed; inset: 0;
  pointer-events: none;
  background-image: radial-gradient(rgba(22,24,29,0.035) 1px, transparent 1px);
  background-size: 3px 3px;
  opacity: 0.45;
  z-index: 0;
  mix-blend-mode: multiply;
}

.serif { font-family: 'Fraunces', 'Iowan Old Style', Georgia, serif; font-optical-sizing: auto; }
.mono  { font-family: 'JetBrains Mono', ui-monospace, 'Menlo', monospace; font-feature-settings: 'tnum'; }

/* ── Header ───────────────────────────────────────────────────── */
.uvo-header {
  background: var(--paper) !important;
  border-bottom: 1px solid var(--rule);
  box-shadow: none !important;
  height: 64px;
}
.uvo-wordmark {
  font-family: 'Fraunces', serif;
  font-weight: 500;
  font-style: italic;
  font-size: 22px;
  font-optical-sizing: auto;
  letter-spacing: -0.02em;
  color: var(--ink);
  position: relative;
  padding-left: 18px;
  display: inline-block;
}
.uvo-wordmark::before {
  content: "§";
  position: absolute;
  left: 0; top: 50%;
  transform: translateY(-54%);
  color: var(--accent);
  font-style: normal;
  font-weight: 400;
  font-size: 26px;
  line-height: 1;
}
.uvo-kicker {
  font-family: 'Manrope', sans-serif;
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 500;
}
.uvo-tally {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.05em;
}
.uvo-tally b { color: var(--ink); font-weight: 500; }

/* ── Sidebar ──────────────────────────────────────────────────── */
.uvo-drawer {
  background: var(--paper) !important;
  border-right: 1px solid var(--rule);
  box-shadow: none !important;
  padding-top: 24px;
}
.uvo-nav-label {
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 600;
  padding: 0 20px 10px;
  border-bottom: 1px solid var(--rule-soft);
  margin: 0 0 8px;
}
.uvo-nav-item {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 10px 20px;
  color: var(--ink-2);
  cursor: pointer;
  font-family: 'Fraunces', serif;
  font-weight: 400;
  font-size: 17px;
  letter-spacing: -0.01em;
  border-left: 2px solid transparent;
  transition: background 120ms, color 120ms, border-color 120ms;
}
.uvo-nav-item:hover { background: var(--muted-bg); color: var(--ink); }
.uvo-nav-item .num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--ink-3);
  letter-spacing: 0.05em;
  font-weight: 400;
}
.uvo-nav-item.active {
  color: var(--ink);
  border-left-color: var(--accent);
  background: var(--muted-bg);
  font-style: italic;
}
.uvo-nav-item.active .num { color: var(--accent); }

.uvo-drawer-footer {
  position: absolute;
  bottom: 16px; left: 20px; right: 20px;
  font-size: 10px;
  color: var(--ink-3);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  border-top: 1px solid var(--rule-soft);
  padding-top: 10px;
  font-family: 'JetBrains Mono', monospace;
}

/* ── Search input ─────────────────────────────────────────────── */
.uvo-search .q-field__control {
  background: transparent !important;
  border: none !important;
  border-bottom: 1px solid var(--rule) !important;
  border-radius: 0 !important;
  padding: 0 0 6px !important;
  min-height: 44px;
  box-shadow: none !important;
}
.uvo-search .q-field__control::before,
.uvo-search .q-field__control::after { display: none !important; }
.uvo-search input {
  font-family: 'Fraunces', serif !important;
  font-size: 22px !important;
  font-weight: 400 !important;
  color: var(--ink) !important;
  letter-spacing: -0.015em;
}
.uvo-search input::placeholder {
  font-style: italic;
  color: var(--ink-3) !important;
  opacity: 1;
}
.uvo-search:focus-within .q-field__control {
  border-bottom-color: var(--accent) !important;
}

.uvo-autocomplete {
  background: var(--paper-2);
  border: 1px solid var(--rule);
  box-shadow: 0 18px 40px -18px rgba(22,24,29,0.25);
  border-radius: 2px;
}
.uvo-autocomplete .row {
  padding: 10px 14px;
  border-bottom: 1px solid var(--rule-soft);
  cursor: pointer;
}
.uvo-autocomplete .row:last-child { border-bottom: 0; }
.uvo-autocomplete .row:hover { background: var(--muted-bg); }
.uvo-autocomplete .type {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--accent-2);
  min-width: 64px;
}

/* ── Table ────────────────────────────────────────────────────── */
.uvo-table {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
.uvo-table .q-table__top,
.uvo-table .q-table__bottom {
  background: transparent !important;
  padding: 10px 0 !important;
  border: none !important;
}
.uvo-table table { border-collapse: collapse !important; }
.uvo-table thead tr th {
  background: transparent !important;
  border-top: 1px solid var(--ink);
  border-bottom: 1px solid var(--rule);
  font-family: 'Manrope', sans-serif !important;
  font-size: 10px !important;
  text-transform: uppercase !important;
  letter-spacing: 0.18em !important;
  color: var(--ink-3) !important;
  font-weight: 600 !important;
  padding: 12px 14px !important;
}
.uvo-table tbody tr td {
  border-bottom: 1px solid var(--rule-soft) !important;
  padding: 16px 14px !important;
  background: transparent !important;
  color: var(--ink-2);
  font-size: 13px;
  vertical-align: baseline;
}
.uvo-table tbody tr:hover td { background: var(--muted-bg) !important; }
.uvo-table tbody tr.selected td { background: var(--selected-bg) !important; }

.uvo-cell-title {
  font-family: 'Fraunces', serif;
  font-weight: 400;
  font-size: 16px;
  color: var(--ink);
  letter-spacing: -0.01em;
  line-height: 1.25;
}
.uvo-cell-procurer { color: var(--ink-2); font-size: 12.5px; }
.uvo-cell-mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--ink-2);
}
.uvo-cell-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12.5px;
  color: var(--ink);
  font-weight: 500;
}
.uvo-cell-value.none { color: var(--ink-3); font-weight: 400; }

/* ── Detail panel (the big one) ───────────────────────────────── */
.uvo-detail {
  background: var(--paper-2);
  border-left: 1px solid var(--rule);
  border-top: 1px solid var(--rule);
  position: relative;
  overflow: hidden;
}
.uvo-detail::before {
  content: "";
  position: absolute; top: 0; left: 0; right: 0; height: 4px;
  background: var(--accent);
}
.uvo-detail-empty {
  font-family: 'Fraunces', serif;
  font-style: italic;
  font-size: 20px;
  color: var(--ink-3);
  letter-spacing: -0.01em;
}
.uvo-detail-empty .hint {
  font-family: 'Manrope', sans-serif;
  font-style: normal;
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-top: 12px;
}
.uvo-detail-kicker {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--accent);
  display: flex;
  align-items: center;
  gap: 10px;
}
.uvo-detail-kicker .bar {
  flex: 1;
  height: 1px;
  background: var(--rule);
}
.uvo-detail-title {
  font-family: 'Fraunces', serif;
  font-weight: 400;
  font-size: 36px;
  line-height: 1.08;
  letter-spacing: -0.025em;
  color: var(--ink);
}
.uvo-detail-title em {
  font-style: italic;
  color: var(--accent);
}
.uvo-detail-procurer {
  font-family: 'Fraunces', serif;
  font-style: italic;
  font-size: 17px;
  color: var(--ink-2);
  letter-spacing: -0.01em;
}
.uvo-detail-section-label {
  font-family: 'Manrope', sans-serif;
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 600;
  margin-bottom: 6px;
}
.uvo-detail-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  color: var(--ink);
  letter-spacing: 0;
}
.uvo-detail-value.big {
  font-family: 'Fraunces', serif;
  font-size: 28px;
  font-weight: 400;
  letter-spacing: -0.02em;
  color: var(--ink);
}
.uvo-detail-value.big .unit {
  font-size: 16px;
  color: var(--accent);
  margin-left: 6px;
  font-style: italic;
}
.uvo-detail-desc {
  font-family: 'Fraunces', serif;
  font-size: 15.5px;
  line-height: 1.55;
  color: var(--ink-2);
  letter-spacing: -0.005em;
  column-count: 1;
}
.uvo-detail-desc::first-letter {
  font-size: 1.8em;
  float: left;
  line-height: 0.9;
  padding: 4px 8px 0 0;
  font-weight: 500;
  color: var(--accent);
}
.uvo-metagrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 22px 32px;
  border-top: 1px solid var(--rule-soft);
  border-bottom: 1px solid var(--rule-soft);
  padding: 22px 0;
}
.uvo-award-row {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: baseline;
  gap: 14px;
  padding: 12px 0;
  border-bottom: 1px dashed var(--rule-soft);
}
.uvo-award-row:last-child { border-bottom: 0; }
.uvo-award-row .idx {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--ink-3);
  letter-spacing: 0.05em;
}
.uvo-award-row .name {
  font-family: 'Fraunces', serif;
  font-size: 16px;
  color: var(--ink);
  letter-spacing: -0.01em;
}
.uvo-award-row .meta {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-3);
  margin-top: 2px;
}
.uvo-award-row .val {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: var(--ink);
}

.uvo-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border: 1px solid var(--rule);
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-2);
  background: var(--paper);
}
.uvo-pill.accent { color: var(--accent); border-color: var(--accent); }
.uvo-close {
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--rule);
  background: var(--paper);
  cursor: pointer;
  color: var(--ink-2);
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  transition: background 120ms, color 120ms;
  border-radius: 0;
}
.uvo-close:hover { background: var(--ink); color: var(--paper); }

/* Pagination */
.uvo-table .q-pagination .q-btn,
.uvo-table .q-select__dropdown-icon,
.uvo-table .q-table__bottom {
  color: var(--ink-2) !important;
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 11px !important;
  letter-spacing: 0.05em !important;
}

/* Spinner */
.q-spinner { color: var(--accent) !important; }

/* Scrollbars in detail panel */
.uvo-detail ::-webkit-scrollbar { width: 10px; }
.uvo-detail ::-webkit-scrollbar-thumb { background: var(--rule); border-radius: 0; }
.uvo-detail ::-webkit-scrollbar-track { background: transparent; }
</style>
"""


def apply_theme() -> None:
    """Inject the global stylesheet exactly once per process."""
    global _APPLIED
    if _APPLIED:
        return
    ui.add_head_html(_HEAD_HTML)
    _APPLIED = True
