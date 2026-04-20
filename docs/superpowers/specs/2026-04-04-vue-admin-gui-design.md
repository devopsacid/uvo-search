# UVO Admin GUI — Design Spec

**Date:** 2026-04-04  
**Status:** Approved  
**Scope:** New Vue 3 admin frontend + FastAPI analytics backend

---

## Context

The existing stack has a NiceGUI frontend (port 8080) for general users and a FastMCP server (port 8000) exposing tools against MongoDB + Neo4j (populated by the `uvo_pipeline`). This design adds an admin-oriented GUI for two audiences:

1. **Executive / decision makers** — need bird's-eye KPI dashboards, spend trends, top supplier rankings, cost breakdowns by category.
2. **Investigators / auditors** — need deep drill-down into contracts, supplier profiles, procurer relationships, and money flows.

Neither audience is served by the current NiceGUI app, which is a search tool, not an analytics platform.

---

## Architecture

Three new components are added. The existing MCP server and NiceGUI frontend are unchanged.

```
Browser (admin users)
  └─► Vue 3 Admin GUI          src/uvo-gui-vuejs/   port 3000
        └─► FastAPI Analytics  src/uvo_api/         port 8001
              └─► FastMCP Server (existing)         port 8000
                    └─► MongoDB + Neo4j (populated by uvo_pipeline)
```

**New Docker services:**
- `admin-gui` — serves the built Vue app (Nginx) or Vite dev server
- `api` — FastAPI analytics service

**New directories:**
- `src/uvo-gui-vuejs/` — Vue 3 application
- `src/uvo_api/` — FastAPI analytics service
- `Dockerfile.admin-gui`
- `Dockerfile.api`

---

## Tech Stack

### Frontend (`src/uvo-gui-vuejs/`)
- **Vue 3** with Composition API + `<script setup>`
- **Vite** — build tooling
- **Vue Router 4** — client-side routing
- **Pinia** — state management (global company filter, theme)
- **Chart.js + vue-chartjs** — bar charts, donut charts
- **Tailwind CSS** — utility-first styling (replaces component library)
- **vue-i18n** — Slovak (default) / English language toggle

### Backend (`src/uvo_api/`)
- **FastAPI** — REST API framework
- **httpx** — async HTTP client to call MCP server
- **Pydantic v2** — response models
- Reuses existing `uvo_mcp` config patterns (env vars, settings class)

---

## Pages & Routing

| Route | Page | Description |
|---|---|---|
| `/` | Dashboard | Global KPIs, spend chart, CPV breakdown, top suppliers/procurers, recent contracts |
| `/contracts` | Contracts | Searchable/filterable table + slide-over detail panel |
| `/suppliers` | Suppliers | Search by name or IČO → card grid |
| `/suppliers/:ico` | Supplier Detail | Company dashboard: KPIs, contract list, spend trend, procurer relationships |
| `/procurers` | Procurers | Search by name or IČO → card grid |
| `/procurers/:ico` | Procurer Detail | Company dashboard: KPIs, contract list, spend trend, top suppliers used |
| `/costs` | Cost Analysis | Spend by CPV, year-over-year comparison, top contracts by value |
| `/search` | Search | Global full-text search across contracts, suppliers, procurers |

**No Persons page** — current data sources do not expose individual person data. Person–company connections are covered via Supplier/Procurer detail pages using IČO. A dedicated Persons page is deferred until RPVS/ORSR integration (Tier 2/3 data sources).

---

## Navigation

**Top navigation bar** (horizontal, full-width content below):
- Left: logo "UVO Admin"
- Center: nav items — Dashboard · Zákazky · Dodávatelia · Obstarávatelia · Náklady · Hľadať
- Right: **global company filter** (search dropdown — pick any procurer or supplier to scope the whole dashboard) + **SK/EN toggle** + **🌙 dark mode toggle**

Active item highlighted with bottom border in `#38bdf8` (cyan).

---

## Dashboard Page

**Global company filter:** A search-as-you-type dropdown in the top nav. When a company is selected, all dashboard widgets filter to that company's data. When cleared, shows global aggregated data.

**KPI cards row (4 cards):**
- Celková hodnota (total spend) — blue left border
- Počet zákaziek (contract count) — green left border
- Priemerná hodnota (avg value) — red left border
- Aktívni dodávatelia (active suppliers) — purple left border

Each card shows delta vs. previous year.

**Charts row (2 columns):**
- Left (2/3 width): Bar chart — spend by year (€M)
- Right (1/3 width): Donut chart — spend by CPV category with legend

**Bottom row (2 columns):**
- Left: Recent contracts table (title, procurer, value, status badge)
- Right: Top 5 suppliers ranked by total value with inline bar

Clicking any supplier name or procurer name navigates to their detail page (`/suppliers/:ico` or `/procurers/:ico`).

---

## Company Detail Pages (Supplier & Procurer)

Both share the same layout pattern:

1. **Header:** Company name, IČO, badge (Dodávateľ / Obstarávateľ)
2. **KPI row:** contracts won/issued, total value, avg value, years active
3. **Spend trend chart:** bar chart of annual spend for this company
4. **Contracts table:** all contracts for this company, filterable by year/value
5. **Relationship panel:**
   - Supplier detail: procurers they've won contracts from (ranked)
   - Procurer detail: suppliers they've awarded contracts to (ranked)

---

## Contracts Page

- Full-width filterable data table
- Filters: free text, CPV code, date range (from/to), value range (min/max)
- Columns: title, procurer, supplier, value, CPV, year, status
- Row click → slide-over panel on the right with full contract detail (all fields, link to source record)
- Pagination: server-side (offset/limit)

---

## Cost Analysis Page

- Spend breakdown by CPV category — horizontal bar chart (sortable by value)
- Year-over-year comparison table — categories as rows, years as columns
- Top 20 contracts by value — table with link to detail
- Filter: by procurer or supplier (reuses global company filter)

---

## Visual Design

**Light mode (default):**
- Background: `#f1f5f9` (slate-100)
- Cards: white with `box-shadow: 0 1px 3px rgba(0,0,0,0.07)`
- KPI left borders: blue / green / red / purple
- Accent: `#2563eb` (blue-600)
- Nav background: `#1e293b` (slate-800)
- Text: `#0f172a` / `#475569` / `#94a3b8`

**Dark mode (toggle):**
- Background: `#0f172a`
- Cards: `#1e293b`
- Accent: `#38bdf8` (cyan)
- Charts: vivid neon palette

**Typography:** System font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`)

**Localisation:** vue-i18n, Slovak (`sk`) default, English (`en`) toggle. All UI labels translated; data (company names, contract titles) displayed as returned by API.

---

## FastAPI Analytics API (`src/uvo_api/`, port 8001)

All endpoints are async. Dashboard endpoints accept optional `?ico=<string>&entity_type=supplier|procurer` to scope to a single company.

### Dashboard endpoints
```
GET /api/dashboard/summary        → { total_value, contract_count, avg_value, active_suppliers, deltas }
GET /api/dashboard/spend-by-year  → [{ year, total_value }]
GET /api/dashboard/top-suppliers  → [{ ico, name, total_value, contract_count }]  (top 5)
GET /api/dashboard/top-procurers  → [{ ico, name, total_spend, contract_count }]  (top 5)
GET /api/dashboard/by-cpv         → [{ cpv_code, label, total_value, percentage }]
GET /api/dashboard/recent         → [{ id, title, procurer, value, status, year }]  (last 10)
```

### Contract endpoints
```
GET /api/contracts                → paginated list (filters: q, cpv, date_from, date_to, value_min, value_max, ico)
GET /api/contracts/{id}           → full contract detail
```

### Supplier endpoints
```
GET /api/suppliers                → paginated search (q, ico)
GET /api/suppliers/{ico}          → supplier profile + contracts
GET /api/suppliers/{ico}/summary  → KPIs for company dashboard
```

### Procurer endpoints
```
GET /api/procurers                → paginated search (q, ico)
GET /api/procurers/{ico}          → procurer profile + contracts
GET /api/procurers/{ico}/summary  → KPIs for company dashboard
```

### Implementation approach
The API calls the FastMCP server using HTTP calls (same pattern as `uvo_gui/mcp_client.py`). For aggregations (spend by year, CPV breakdown, top-N) it fetches multiple pages from the MCP tools and aggregates in Python. Response models use Pydantic v2.

---

## Backend Gaps & Recommendations

The following features require data not currently available from the 4 existing MCP tools. These are recommendations for future backend work:

| Feature | Gap | Recommendation |
|---|---|---|
| Spend-by-year aggregation | MCP returns flat lists | Aggregate in FastAPI (acceptable for MVP, add caching) |
| CPV category labels | Records carry raw CPV codes | Maintain a CPV code→label mapping file in `src/uvo_api/data/cpv_labels.json` |
| Contract status (active/closed) | Not in current MCP response | Map from `year` field as proxy (current year = active); proper status needs Vestník XML (Tier 3) |
| Persons / beneficial owners | Not in current sources | Requires RPVS integration (Tier 2) — deferred |
| Financial health of suppliers | Not in current sources | Requires FinStat integration (Tier 3) — deferred |
| Year-over-year deltas | Requires two aggregation passes | Compute in FastAPI from two date-range queries |

---

## Project Structure

```
src/
├── uvo-gui-vuejs/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/index.ts
│   │   ├── stores/
│   │   │   ├── filter.ts        # global company filter (Pinia)
│   │   │   └── theme.ts         # dark/light mode (Pinia)
│   │   ├── i18n/
│   │   │   ├── sk.ts
│   │   │   └── en.ts
│   │   ├── api/
│   │   │   └── client.ts        # axios/fetch wrapper for uvo_api
│   │   ├── components/
│   │   │   ├── TopNav.vue
│   │   │   ├── KpiCard.vue
│   │   │   ├── SpendBarChart.vue
│   │   │   ├── CpvDonutChart.vue
│   │   │   ├── ContractTable.vue
│   │   │   ├── ContractSlideOver.vue
│   │   │   ├── SupplierCard.vue
│   │   │   ├── CompanyFilter.vue
│   │   │   └── TopRankingList.vue
│   │   └── pages/
│   │       ├── DashboardPage.vue
│   │       ├── ContractsPage.vue
│   │       ├── SuppliersPage.vue
│   │       ├── SupplierDetailPage.vue
│   │       ├── ProcurersPage.vue
│   │       ├── ProcurerDetailPage.vue
│   │       ├── CostAnalysisPage.vue
│   │       └── SearchPage.vue
│
├── uvo_api/
│   ├── __main__.py
│   ├── app.py               # FastAPI app, CORS, router registration
│   ├── config.py            # Settings (UVO_API_PORT, MCP_SERVER_URL)
│   ├── mcp_client.py        # Reuse pattern from uvo_gui/mcp_client.py
│   ├── models.py            # Pydantic response models
│   ├── data/
│   │   └── cpv_labels.json  # CPV code → Slovak/English label map
│   └── routers/
│       ├── dashboard.py
│       ├── contracts.py
│       ├── suppliers.py
│       └── procurers.py
```

---

## Verification

After implementation, verify end-to-end:

1. `cd src/uvo-gui-vuejs && npm run dev` — Vue app starts on port 3000
2. `uv run python -m uvo_api` — FastAPI starts on port 8001
3. Open `http://localhost:3000` — dashboard loads with real data from MongoDB/Neo4j
4. Global company filter: select a procurer → all KPIs and charts update
5. Click a supplier name → navigates to `/suppliers/:ico` with company dashboard
6. Contracts page: filter by CPV code, verify table updates
7. Dark mode toggle: switches theme correctly
8. SK/EN toggle: all labels switch language, data stays in Slovak
9. `pytest tests/api/ -v` — FastAPI endpoint tests pass
10. Docker Compose: `docker compose up` — all 4 services healthy
