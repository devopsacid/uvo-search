# uvo-gui-react

**React 18 + Vite 5 + TypeScript** single-page application (SPA) for browsing Slovak government procurement data.

All data flows through the `uvo_api` backend (port 8001), which proxies to the MCP server (port 8000).

## Quick Start

```bash
npm install
npm run dev    # Vite dev server on http://localhost:5174, /api proxied to :8001
npm run build  # Production build to dist/
npm run test   # Vitest unit tests + coverage
npm run lint   # ESLint check
```

## Tech Stack

- **React 18** — UI library
- **Vite 5** — Fast bundler with HMR
- **TypeScript** (strict mode) — Type safety
- **React Router 6** — Client-side routing
- **TanStack Query 5** — Data fetching & caching
- **Tailwind CSS 3** — Styling
- **shadcn/ui** — Accessible component library
- **Recharts** — Data visualizations
- **Cytoscape.js** — Network graph rendering (lazy-loaded)
- **Vitest + Testing Library** — Unit testing
- **ESLint + Prettier** — Code quality

## Pages

- `/` — Overview dashboard
- `/search` — Search procurements (full-text + filters)
- `/suppliers` — Browse suppliers by name/ICO
- `/suppliers/:ico` — Supplier detail & contract history
- `/procurers` — Browse procurers (authorities)
- `/procurers/:ico` — Procurer detail & spending analysis
- `/graph` — Interactive network visualization
- `/cpv-trends` — CPV code trends over time
- `/procurers/:ico/concentration` — HHI supplier concentration
- `/calendar` — Timeline view
- `/about` — Project info

## Architecture Notes

- **URL-as-state:** Pagination, filters, sort live in query params → bookmarkable, shareable URLs
- **Internationalization:** All Slovak strings in `src/i18n/sk.ts`; use `t("key")` from context
- **Utilities:** `cn()` function (`src/lib/utils.ts`) for Tailwind class merging (via clsx)
- **No global state:** TanStack Query handles server state; React hooks for UI state
- **Lazy graph chunk:** Cytoscape.js code-split; wrapped in `<Suspense>` fallback

## Docker

Built as part of the repo stack:

```bash
docker compose up gui-react   # serves on http://localhost:8080
```

Internal service URL (within Docker): `http://gui-react:80/` (built from Vite dev port 5174)
