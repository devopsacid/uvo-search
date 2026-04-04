# UVO Search — NiceGUI UI Redesign

**Date:** 2026-04-03  
**Status:** Approved

## Summary

Redesign the NiceGUI frontend with a persistent sidebar, light theme, Quasar layout primitives, and a split-panel search page. Add three missing subpages: Obstaravatelia, Dodavatelia, and O aplikácii.

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Navigation | Sidebar (left, persistent) | More space for labels, scales to future sections |
| Theme | Light (white bg, blue accents) | Readable for dense data tables |
| Layout engine | NiceGUI Quasar primitives (`ui.left_drawer`, `ui.header`, `ui.page_container`) | Responsive, accessible, handles sidebar toggle natively |
| Search results | Split panel (list left, detail right) | Avoids dialog popup; faster to browse results |
| Procurers/Suppliers pages | Search + card grid | Matches MCP tool capabilities |
| About page | Minimal text | No extra content needed |

---

## Architecture

### Layout Shell

A shared `layout()` context manager in `src/uvo_gui/components/layout.py` wraps every page. It uses:

- `ui.header` — app name "UVO Search" with subtitle
- `ui.left_drawer` — persistent sidebar with nav links
- `ui.page_container` — content area

Each page calls `with layout():` and renders its content inside. The active nav item is highlighted based on the current route.

The existing `components/nav_header.py` is replaced by this layout component.

### Pages

| Route | File | Description |
|---|---|---|
| `/` | `pages/search.py` | Search + split panel |
| `/procurers` | `pages/procurers.py` | Obstaravatelia search + card grid |
| `/suppliers` | `pages/suppliers.py` | Dodavatelia search + card grid |
| `/about` | `pages/about.py` | Minimal about text |

All four routes are registered in `app.py`.

---

## Page Designs

### 1. Vyhľadávanie (`/`)

**Left panel (fixed ~280px):**
- Search card: keyword input, date-from/date-to inputs, "Hľadať" button
- Results list: scrollable, each row shows title (blue link style), procurer, value (green), date
- Active/selected row highlighted with blue left border and light blue background
- Pagination bar at the bottom: "← Predch." / "page X / Y" / "Ďalšia →"
- Result count shown above list

**Right panel (flex):**
- Empty state when nothing selected: "Vyberte zákazku zo zoznamu"
- When a row is selected, shows:
  - Title (h2-weight)
  - Status badge + CPV badge
  - 2×2 info card grid: Obstarávateľ, Hodnota (green, large), Dátum, CPV kód
  - Dodávatelia section: list of supplier cards with name, IČO, "Víťaz" badge

**State:** `SearchState` dataclass extended with `selected_item: dict | None = None`. Clicking a row sets `selected_item` and calls `results_view.refresh()`. No dialog needed.

### 2. Obstaravatelia (`/procurers`)

- Search input + "Hľadať" button
- Results: responsive card grid (3 columns on wide screens)
- Each card: org name, contract count, total value in EUR
- Uses MCP tool `find_procurer` (or equivalent search tool)
- Loading spinner while fetching, error card on failure

### 3. Dodavatelia (`/suppliers`)

- Search input (name or IČO) + "Hľadať" button  
- Results: responsive card grid (3 columns on wide screens)
- Each card: company name, IČO, contract count, total value won
- Uses MCP tool `find_supplier` (or equivalent search tool)
- Loading spinner while fetching, error card on failure

### 4. O aplikácii (`/about`)

- Page title: "O aplikácii UVO Search"
- One paragraph describing the app in Slovak
- Data source attribution: `uvo.gov.sk · ted.europa.eu`
- No dynamic data

---

## Visual Style

| Element | Style |
|---|---|
| Background | `#f1f5f9` (slate-100) |
| Sidebar bg | `#ffffff` with right border `#e2e8f0` |
| Cards/panels | `#ffffff` border `#e2e8f0` radius `8px` |
| Primary blue | `#1d4ed8` |
| Active nav item | `background: #dbeafe`, `color: #1d4ed8` |
| Positive value | `#059669` (green) |
| Muted text | `#6b7280` |
| Badge (CPV) | blue pill — `#dbeafe` / `#1d4ed8` |
| Badge (status) | green pill — `#dcfce7` / `#166534` |

Styling is applied via `ui.add_head_html()` injecting a `<style>` block, or inline NiceGUI `.classes()` / `.style()` calls using Tailwind-compatible values.

---

## File Changes

| File | Action |
|---|---|
| `src/uvo_gui/components/layout.py` | **Create** — shared Quasar layout context manager |
| `src/uvo_gui/components/nav_header.py` | **Delete** — replaced by layout.py |
| `src/uvo_gui/components/detail_dialog.py` | **Delete** — replaced by inline split panel |
| `src/uvo_gui/pages/search.py` | **Rewrite** — split panel, extend SearchState |
| `src/uvo_gui/pages/procurers.py` | **Create** |
| `src/uvo_gui/pages/suppliers.py` | **Create** |
| `src/uvo_gui/pages/about.py` | **Create** |
| `src/uvo_gui/app.py` | **Update** — register 3 new routes, remove old nav_header import |

---

## Out of Scope

- Clicking a procurer/supplier card to drill into their contracts (future)
- Mobile responsive sidebar toggle (Quasar handles it, but no custom styling needed now)
- Dark mode
