# UVO Admin GUI — Terminal Redesign

**Date:** 2026-04-19
**Branch:** `feature/admin-redesign`
**Target:** `src/uvo-gui-vuejs/` (the Vue 3 admin SPA served via `Dockerfile.admin-gui`)

## Goal

Replace the current generic SaaS dashboard look with a dense, monospaced, amber-on-black **Bloomberg terminal aesthetic**. One-shot full rewrite of all 8 pages plus the global shell.

## Non-goals

- No backend, MCP, FastAPI, or NiceGUI changes
- No new data endpoints — all calls stay on the existing `api/client.ts`
- No change to routing paths (`/`, `/contracts`, `/suppliers`, `/procurers`, `/costs`, `/search`, `/suppliers/:ico`, `/procurers/:ico`)
- No i18n message-key renames — only additions for new UI chrome

## Visual language

| Token | Value |
|---|---|
| `ink.950` (bg) | `#0b0d0f` |
| `ink.900` (panel) | `#0b0d0f` (same — panels defined by borders) |
| `ink.800` (chrome) | `#141618` |
| `ink.700` (divider) | `#2a2d30` |
| `fg.primary` | `#d6d7d4` |
| `fg.muted` | `#8a8e92` |
| `fg.dim` | `#6a6e72` |
| `accent` | `#ff9e1f` (amber) |
| `up` | `#3fb950` (positive delta, "up") |
| `down` | `#f85149` (negative delta, "down") |
| Font | JetBrains Mono (via `@fontsource/jetbrains-mono` 400/500/700) |
| Body size | 12px default, 11px in tables, 10px in labels |
| Radius | `0` everywhere |
| Shadows | none |
| Numeric cells | `font-variant-numeric: tabular-nums` |

Dark-only. Previous `stores/theme.ts` and the sun/moon toggle are removed.

## Architecture

```
App.vue
├── TickerBar.vue          (persistent: total value, contracts, avg, suppliers)
├── TopNav.vue              (menu-bar style; hotkey hints)
├── <RouterView />         (pages)
└── StatusBar.vue           (last sync · record count · ? HELP · SK/EN)

CommandPalette.vue (mounted once in App.vue, opened by ⌘K / Ctrl+K)
```

### New shared primitives (`src/components/`)

| File | Responsibility |
|---|---|
| `TickerBar.vue` | Reads summary from Pinia; shows 4 KPIs + up/down deltas + timestamp; subscribes to `filter` store so deltas stay scoped |
| `TopNav.vue` (rewrite) | Links: Overview · Contracts · Suppliers · Procurers · Costs · Network · Search · Graph. Active item in amber with underline. Each shows its hotkey hint (`[D]`, `[C]`, `[S]`, etc.) |
| `StatusBar.vue` | Fixed bottom strip. Left: keyboard cheat-sheet. Right: last-sync timestamp, SK/EN toggle styled as a status item |
| `Panel.vue` | Props: `title`, `action?` (slot). Renders `> TITLE` header + bordered body. Used everywhere as the new box primitive, replacing ad-hoc card divs |
| `DataRow.vue` | Props: `cols` (array of widths). Renders a tabular row with mono font + tabular nums + hover row-highlight. Used by ranking lists and mini tables inside panels |
| `Kpi.vue` | Key-value row for use inside a `Panel`. Props: `label`, `value`, `delta?`, `deltaDir?` (`up`/`down`) |
| `CommandPalette.vue` | ⌘K modal. Fuzzy-matches static page list + calls `search_autocomplete` for entities. `Enter` to navigate, `Esc` to close |

### New composables (`src/composables/`)

| File | Responsibility |
|---|---|
| `useHotkeys.ts` | Registers global key handler. Chord support (`g` then `d`). Bindings: `g d` → `/`, `g c` → `/contracts`, `g s` → `/suppliers`, `g p` → `/procurers`, `g x` → `/costs`, `g n` → `/network` (graph), `g /` → `/search`, `/` → focus search, `⌘K`/`Ctrl+K` → open palette, `?` → show cheat-sheet, `Esc` → close modals |
| `useCommandPalette.ts` | Tiny Pinia-style singleton (reactive ref) for open/close state |

### Removed

- `stores/theme.ts` and all `document.documentElement.classList.toggle('dark', …)` plumbing
- `KpiCard.vue` (replaced by `Panel` + `Kpi`)
- `EntityCard.vue` (replaced by `Panel` + detail content)
- `TopRankingList.vue` (replaced by `Panel` + `DataRow` loop)
- `KpiCard.test.ts`

### Charts

`components/charts/chartDefaults.ts` exports a single `applyTerminalChartDefaults()` helper that sets:
- Colors: series → `#ff9e1f`, grid → `#2a2d30`, ticks → `#8a8e92`
- Font family → JetBrains Mono, size 10
- Animations → disabled (`animation: false`)
- Legend → hidden by default

`SpendBarChart.vue` and `CpvDonutChart.vue` rebuild options with this helper. The Donut becomes a narrow horizontal bar stack when there's room (decided per-page, not globally).

### Graph page

`GraphPage.vue` keeps vis-network. New `graphOptions.dark.ts` with:
- `nodes.color.background` → `#141618`, `border` → `#ff9e1f`
- `edges.color.color` → `#2a2d30`, highlight → `#ff9e1f`
- `nodes.font` → `{ color: '#d6d7d4', face: 'JetBrains Mono', size: 11 }`
- Background via CSS on the container, not vis-network

## Page-by-page behavior

All pages use the same outer shell (`TickerBar` + `TopNav` + `StatusBar`). Differences are in the body.

### Dashboard (`/`) — `DashboardPage.vue`
3-column panel grid (matches mockup):
- Row 1: `KEY METRICS` panel (7 KPIs list) | `SPEND · 8Y` panel (line sparkline) | `TOP SUPPLIERS` panel (DataRow list)
- Row 2: `RECENT CONTRACTS · LAST 10` full-width panel

### Contracts (`/contracts`) — `ContractsPage.vue`
- Filter strip (year, CPV, value range) above a full-width `ContractTable`
- Table is mono, 11px, sticky header, hover row highlight, no zebra stripes
- Row click opens `ContractSlideOver` (keep logic, restyle)

### Suppliers (`/suppliers`) — `SuppliersPage.vue`
- Search box + filters at top
- Full-width table: rank, ICO, name, total value, contract count, % of total
- Row click → `/suppliers/:ico`

### Procurers (`/procurers`) — `ProcurersPage.vue`
- Same shape as Suppliers

### Cost analysis (`/costs`) — `CostAnalysisPage.vue`
- 2×2 panel grid: CPV breakdown, region breakdown, supplier concentration (HHI), year-over-year

### Search (`/search`) — `SearchPage.vue`
- Terminal-prompt styled input: `$ search >` prefix in amber
- Results as `DataRow` groups (Contracts, Suppliers, Procurers), with section headers

### Supplier detail (`/suppliers/:ico`) — `SupplierDetailPage.vue`
- Entity header panel (name, ICO, address, totals)
- 3-col panel grid: top procurers, spend by year, CPV breakdown
- Full-width contracts table panel below

### Procurer detail (`/procurers/:ico`) — `ProcurerDetailPage.vue`
- Same shape as Supplier detail

## i18n

Add keys to `src/i18n/locales/sk.json` and `en.json`:
- `statusBar.lastSync`
- `statusBar.records`
- `statusBar.help`
- `palette.placeholder`
- `palette.pages`
- `palette.entities`
- `hotkeys.title`, `hotkeys.goto`, `hotkeys.search`, `hotkeys.palette`, `hotkeys.close`
- `ticker.totalValue`, `ticker.contracts`, `ticker.avgValue`, `ticker.suppliers`

No existing keys are renamed.

## Testing

Existing tests under `src/__tests__/` or co-located (`TopNav.test.ts`, `ContractTable.test.ts`, `KpiCard.test.ts`):
- `KpiCard.test.ts` → deleted (component gone)
- `TopNav.test.ts` → rewritten against new markup (role-based queries, active class on amber)
- `ContractTable.test.ts` → updated selectors (mono rows, no card wrapper)

New tests (small surface):
- `Panel.test.ts` — renders title in amber uppercase, slot content
- `Kpi.test.ts` — renders delta in up/down color based on `deltaDir`
- `CommandPalette.test.ts` — opens on `⌘K`, filters list, Enter navigates
- `useHotkeys.test.ts` — chord `g d` triggers navigation

Tests run via `docker compose run --rm admin-gui-test npm test` (a new compose service — or reuse build stage of `Dockerfile.admin-gui` with `npm test` as command). No Node install required on host.

## Dev & build

- `package.json` adds `@fontsource/jetbrains-mono` (runtime dep)
- `Dockerfile.admin-gui` — no changes; `npm ci` + `npm run build` continue to work
- `docker-compose.yml` admin-gui service — no changes
- A new compose service `admin-gui-test` (optional) for running `vitest` in CI loop

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| No Node locally — cannot run dev server or tests on host | Use `docker compose up admin-gui` for preview; `docker compose run --rm admin-gui-test` for vitest |
| Chart.js dark-mode contrast | Centralized defaults + manual review of both charts after rebuild |
| vis-network can look muddy on dark | Pre-tune node/edge opacity; test with real network payload |
| Tailwind tree-shaking drops tokens defined only in templates | Ensure all new palette tokens are used in at least one template; add to `safelist` if any are conditional |
| Hotkeys conflict with browser defaults (e.g., `/` in Firefox) | Use `preventDefault()` and check input focus before swallowing keys |

## Out of scope for this PR

- Search result ranking improvements
- Graph filters (stay as-is)
- Real-time data push (ticker timestamp is static `lastSync`)
- Mobile / narrow-viewport layout — terminal aesthetic is desktop-first; min-width 1024px assumed

## Definition of done

- All 8 routes render in new style with no console errors
- ⌘K opens palette, navigates, closes on Esc
- `g d`, `g c`, `g s`, `g p`, `g x`, `g n`, `g /`, `/`, `?` all work
- Existing Vitest suite green inside Docker; new tests added
- Docker build succeeds: `docker build -f Dockerfile.admin-gui .`
- Merged to `main` after review
