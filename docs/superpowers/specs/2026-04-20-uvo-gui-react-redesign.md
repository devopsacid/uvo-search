# UVO Public GUI — React SPA Redesign

Status: draft · 2026-04-20 · Author: architect

Replace `src/uvo_gui/` (NiceGUI 3.9, port 8080, public Slovak frontend) with a React SPA. Add stronger UX and more dashboards. Backend stays as-is; we go through `uvo_api` (FastAPI, port 8001).

## Current state (NiceGUI app)

| Page | Purpose | MCP tool |
| ---- | ------- | -------- |
| `/search` | Editorial procurement archive, split master/detail (442 lines) | `search_completed_procurements` |
| `/suppliers` | Supplier directory list | `find_supplier` |
| `/procurers` | Contracting authority directory | `find_procurer` |
| `/graph` | Ego/CPV network viewer | `graph_ego_network`, `graph_cpv_network` |
| `/about` | Static page | — |

Pain points: server-rendered roundtrips per interaction, refresh-storm pattern (`@ui.refreshable` + `view.refresh()`), no URL-as-state (filters lost on reload), no entity detail pages (suppliers/procurers have no `/{ico}` route), Slovak strings hardcoded inline, weak skeleton/loading UX, graph viewer is a single static SVG.

## Vue-vs-React verdict

**Recommendation: option (c) — go with React for the new public app, plan to converge admin-gui to React in a later phase.**

- Vue admin (`src/uvo-gui-vuejs/`) is 8 pages, ~3 months old, low surface area. Migrating it later is cheap.
- React has the deeper ecosystem for the things this app needs: TanStack Query, shadcn/ui, charting + graph viz options, hiring pool.
- Running two JS frameworks side-by-side for one cycle is acceptable; running them indefinitely is not. Add an ADR committing to React as the target stack.
- If the user vetoes a future admin-gui rewrite, accept the dual-framework cost — it's bounded and isolated by Docker service.

## Stack

| Concern | Choice | Why |
| ------- | ------ | --- |
| Build | Vite 5 | Mirrors admin-gui tooling; fast HMR. |
| Framework | React 18 + TS strict | User ask; broad ecosystem. |
| Routing | React Router 6 (data routers) | URL-as-state, loaders for SSR-grade UX without SSR. |
| Server state | TanStack Query v5 | Built-in caching, dedup, retry, suspense — kills the refresh-storm pattern. |
| UI primitives | shadcn/ui (Radix + Tailwind) | Copy-in components, no runtime lock-in, accessible. |
| Styling | Tailwind 3 | Consistent with admin-gui. |
| Charts | Recharts | Composable React API, sufficient for bar/line/donut. |
| Graph viz | Cytoscape.js + `react-cytoscapejs` | Mature, handles 100s of nodes, layout algorithms (cose, dagre). Reagraph rejected: WebGL overkill. |
| Tables | TanStack Table v8 | Headless, keeps shadcn styling. |
| i18n | Hardcoded Slovak `sk` strings via a single `t()` helper or const map | App is Slovak-only; full i18n lib is overkill. Wrap via tiny abstraction so swap is cheap if EN ever needed. |
| Forms | react-hook-form + zod | Standard; only needed for filter forms. |
| Tests | Vitest + Testing Library + Playwright (e2e) | Mirrors admin-gui where possible. |

## Dashboards (5 existing, 3 new)

| # | Dashboard | Data source |
| - | --------- | ----------- |
| 1 | **Search** — full-text procurement archive, faceted filters, master/detail | `search_completed_procurements` |
| 2 | **Suppliers** — directory + detail page (`/suppliers/:ico`) with spend-by-year, top procurers | `find_supplier`, `/suppliers/{ico}/summary` |
| 3 | **Procurers** — directory + detail page with spend-by-year, top suppliers, concentration | `find_procurer`, `/procurers/{ico}/summary`, `find_supplier_concentration` |
| 4 | **Graph** — entity ego network + CPV network, interactive zoom/expand | `graph_ego_network`, `graph_cpv_network`, `find_related_organisations` |
| 5 | **Overview** — landing dashboard: totals, YoY, top suppliers/procurers, recent | `/dashboard/*` (already exists) |
| 6 | **CPV trends** *(new)* — time-series of spend per CPV category, drill-down to contracts | `/dashboard/by-cpv` (extend with `?year_from&year_to` — **new endpoint param**) |
| 7 | **Concentration risk** *(new)* — for any procurer, show supplier-share donut + Herfindahl index | `find_supplier_concentration` (compute HHI client-side) |
| 8 | **Procurement calendar** *(new)* — monthly heatmap of contract publication dates, click cell to filter Search | `search_completed_procurements` aggregation — **new endpoint** `/dashboard/by-month` |

Geographic heatmap deferred — addresses are not currently geo-coded. Open question for user.

## UX principles

1. **Every entity name is a link** to its detail page (`/suppliers/:ico`, `/procurers/:ico`). Currently dead text in NiceGUI app.
2. **Filter state lives in the URL** (`?q=...&year=2024&page=2`). Bookmarkable, shareable, back-button works.
3. **Skeletons, not spinners.** Match the shape of incoming content.
4. **Keyboard-first search.** `/` focuses search, arrow keys navigate suggestions, Enter commits.
5. **No layout shift on data load.** Reserve space for variable content.
6. **Sticky filter sidebar; main pane scrolls independently.**
7. **Empty states with a next action**, never a blank panel.

## API layer

Talk **only** to `uvo_api` (REST, JSON) — no direct MCP from browser, no new BFF. Justification: `uvo_api` already exposes typed Pydantic responses, has CORS configured, and the admin-gui uses it. Reuse, don't fork.

New/extended endpoints needed:
- `GET /dashboard/by-cpv` — add `year_from`, `year_to` query params for the trends dashboard.
- `GET /dashboard/by-month?year=YYYY` — new, monthly bucket counts + value sum, for calendar heatmap.
- `GET /procurers/{ico}/concentration?top_n=10` — wraps `find_supplier_concentration` MCP tool. New.
- `GET /graph/ego/{ico}?hops=2` and `GET /graph/cpv/{cpv}?year=YYYY` — wrap existing MCP graph tools so the browser doesn't speak MCP. New router `routers/graph.py`.

These are additive; no breaking changes to existing endpoints.

## Migration / cutover

**Parallel build, hard cutover.**

- Dev: React SPA on Vite port `5174` (avoid clash with admin-gui `5173`); proxy `/api` → `http://localhost:8001`.
- Docker: new service `gui-react` on host port `8090` during overlap. Cutover swaps it to `8080`, retires `gui` service.
- Build: multi-stage Dockerfile (`Dockerfile.gui-react`) → nginx serving static + reverse-proxying `/api` to `api:8001`.
- Keep NiceGUI `gui` service for **one release** post-cutover behind a feature flag / alt host (`legacy.uvo.local`) for fallback. Delete `src/uvo_gui/` and `Dockerfile.gui` in the *next* release after stability is confirmed (target: 2 weeks of clean uptime).

## File layout

```
src/uvo-gui-react/
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
├── public/
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── router.tsx
    ├── api/                # client.ts (fetch wrapper), types.ts, queries/ (TanStack Query hooks)
    ├── pages/              # SearchPage, SuppliersPage, SupplierDetailPage, ProcurersPage,
    │                       # ProcurerDetailPage, GraphPage, OverviewPage, CpvTrendsPage,
    │                       # ConcentrationPage, CalendarPage, AboutPage
    ├── components/         # ui/ (shadcn), layout/ (Header, Sidebar), charts/, graph/, search/
    ├── hooks/
    ├── lib/                # formatters (money, date), cpv labels, url-state helpers
    ├── i18n/               # sk.ts
    └── styles/
```

## Phases

### Phase 1 — Skeleton + API layer (exit: static deploy works)
- Scaffold Vite project, Tailwind, shadcn baseline, router, layout shell with Slovak nav.
- Implement `api/client.ts` mirroring admin-gui's pattern with TanStack Query wrappers.
- Add `/about` and a stub Overview page hitting `/dashboard/summary`.
- Dockerfile + compose service `gui-react:8090`.
- **Exit:** `docker compose up gui-react` serves the shell at :8090, dashboard summary renders.

### Phase 2 — Core directories + Search (exit: NiceGUI feature parity for search/suppliers/procurers)
- Search page with URL-state filters, skeletons, master/detail, autocomplete.
- Suppliers + Procurers list pages + **new** detail pages (`/suppliers/:ico`, `/procurers/:ico`).
- Shared entity-link component used everywhere.
- **Exit:** all NiceGUI search/directory flows reproduced; entity names clickable; back/forward buttons preserve filters.

### Phase 3 — Graph + dashboards (exit: net-new value vs NiceGUI)
- Graph page using Cytoscape with ego + CPV modes, click-to-expand.
- Overview dashboard (full version with charts).
- CPV trends, concentration risk, calendar dashboards (requires new API endpoints — coordinate with backend).
- **Exit:** all 8 dashboards live; Lighthouse ≥90 perf/a11y on overview & search.

### Phase 4 — Cutover (exit: NiceGUI app retired)
- Move `gui-react` to host port `8080`, route `gui` to `8090` as legacy.
- E2E test pass on prod-like compose stack.
- 2-week soak; then delete `src/uvo_gui/`, `Dockerfile.gui`, related tests, NiceGUI deps from `pyproject.toml`. Update `CLAUDE.md`.
- **Exit:** repo no longer has NiceGUI; docs reflect new stack.

## Open questions / risks

1. **Geo data** — is there enough address/region data on procurers to do a map dashboard? If not, drop or add geocoding to the pipeline (out of scope here).
2. **Auth** — public app currently has none. Is that staying true post-redesign, or do we need rate-limit / login for heavier dashboards?
3. **i18n** — committing to Slovak-only is fine today, but will Czech/English ever be needed? Decision affects whether we wrap strings in `t()` or inline them.
4. **SEO** — public site, no SSR. Acceptable or do we need static prerendering of detail pages for search engines?
5. **Cytoscape bundle size** (~400 KB gzipped). Lazy-load the graph route to keep initial JS lean.
