# Analytical dashboards — technical specification

Date: 2026-10-19 · Baseline: `main` @ `ff3cfc2` · Status: proposed

Companion plan: `docs/plans/2026-10-19-analytics-dashboards-plan.md`.

> **Route note:** this spec predates the English identifier rename and keeps its original Slovak paths
> (`/analytika/*`, `/firma/*`, `/firmy`, `/zakazky`, `/hladaj`, `/api/firma*`) as written. Current routes:
> `/analytics/{overview,concentration,cpv,coverage}`, `/company/:ico/{overview,contracts,network,partners,cpv}`,
> `/companies`, `/contracts`, `/search`; API `/api/companies*`. Old paths redirect (SPA) or are hidden aliases (API).
> See `docs/plans/2026-10-19-english-identifiers.md` §2.

## 1. Summary

Two deliverables under one umbrella, "easy to use analytical dashboards":

- **Part A — product analytics** in the React SPA: four dashboards over Slovak public-procurement data
  (market overview, concentration, CPV sectors, data coverage), one shared URL-backed filter bar,
  drill-down from every chart to the contract list, CSV export, accessible Slovak charts. Backed by a
  new `/api/analytics/*` aggregation surface computed at query time over `notices`.
- **Part B — operational monitoring as code**: Prometheus metrics for API, MCP and workers, three Grafana
  dashboards, alert rules, and a `docker compose --profile monitoring` stack under a new top-level
  `monitoring/` directory. Nothing is pushed to a live Grafana, `stubarag-infra` or Vault.

Everything is additive. Existing `/api/dashboard/*` endpoints and the Firma workspace keep working.

## 2. Inventory — what exists today (verified on `main`)

### 2.1 Backend

| Thing | Where | Notes |
| ----- | ----- | ----- |
| Dashboard router | `src/uvo_api/routers/dashboard.py` (`/api/dashboard/{summary,spend-by-year,top-suppliers,top-procurers,by-cpv,by-month,recent}`) | Full-corpus `$group`s via the `CompanyAnalytics` port. Only `ico`/`entity_type`/`year_from`/`year_to` filters; no date range, no source, no CPV filter. |
| Ops dashboards | `routers/ingestion.py`, `routers/worker_status.py`, `routers/ingestion_log.py` (all `/api/dashboard/...`) | Behind `require_ops_token` (bearer `API_OPS_TOKEN`); expose worker topology and instance ids, so they must stay protected. |
| Analytics adapter | `src/uvo_core/adapters/mongo/analytics.py` | Pipeline builders + `async_ttl_cache`d aggregates (`_spend_by_year_agg`, `_cpv_breakdown_agg`, `_monthly_buckets_agg`, `_top_entities_agg`, `entity_profile` with HHI). `MongoCompanyAnalytics` implements `uvo_core.ports.CompanyAnalytics`. |
| Entity profile with HHI | `analytics.py:build_entity_profile_pipeline` / `entity_profile` | Per-ICO `$facet`: years, top partners, `sum(v)`/`sum(v²)` for HHI. Already the right definition (see §4). |
| Cache | `src/uvo_core/cache.py` | `async_ttl_cache(maxsize, ttl, key_from, depends_on_data=True)`; every data-dependent cache self-registers for `clear_data_caches()`, which the `notices:written` subscriber (`uvo_core/adapters/redis/cache_invalidation.py`) calls. **New caches need no registration.** |
| Indexes | `src/uvo_core/adapters/mongo/loaders.py:ensure_indexes` | `notices`: `{notice_type, publication_date}`, `{procurer.ico, notice_type}`, `{awards.supplier.ico, notice_type}`, `cpv_code`, `source+source_id` (unique), `publication_date`, `ingested_at`, `canonical_id`. No `award_date` index, no `source`-leading index. |
| Pipeline health | `src/uvo_pipeline/health.py:collect(db)` | Per-source totals, last ingested, 24h/7d counts, registry/dedup totals. Already imported by `uvo_api` (allowed by import-linter). |
| Metrics | `src/uvo_workers/metrics.py`, served by `uvo_workers/health.py` on `/metrics` (ports 8091–8096) | Families: `uvo_worker_batches_processed`, `uvo_worker_notices_written`, `uvo_worker_stream_lag{stream}`, `uvo_worker_stream_pending{stream}`, `uvo_worker_dead_letter_length`, `uvo_worker_last_success_timestamp_seconds`, `uvo_worker_redis_connected`. Extractor-specific snapshot keys (`cycles_completed`, `cycles_skipped_locked`, `last_error`) are only in the JSON `/health` body, not Prometheus. |
| API/MCP metrics | none | `/health`, `/readyz` only. No request latency, error rate, cache hit ratio or readiness gauge. `prometheus-client` is already a main dependency. |

### 2.2 Frontend (`src/uvo-gui-react`)

- Chart library: **recharts ^2.12.7** (already code-split into `vendor-charts`). Cytoscape for graphs. No new chart dependency is needed.
- Existing pages: `OverviewPage` (`/`, KPI cards + spend by year + top 10 suppliers/procurers + recent), `CpvTrendsPage` (`/cpv-trends`, year range + CPV share list), Firma workspace (`/firma/:ico/*` with prehľad/zákazky/sieť/partneri/cpv tabs), `ZakazkyPage` (`/zakazky` contract list), `IngestionPage`.
- Reusable bits: `KpiCard`, `SpendByYearChart`, `DonutChart`, `EmptyState`, `Skeleton`, `Table`, `FilterInput`/`FilterSelect`, `EntityAutocomplete`, `useUrlFilters`, `formatCurrency`/`formatNumber`/`formatMillions` (sk-SK, EUR), TanStack Query v5 with key factories, `apiClient.get` with `AbortSignal`.
- URL-as-state convention: `ZakazkyPage` reads `q, year, cpv, procurer_ico, supplier_ico, page, selected`. **Bug:** it reads `procurer_ico` from the URL but never sends it to the API (only `ico = supplier_ico`), and it has no `date_from/date_to` or `source` support. Drill-down depends on fixing this.
- i18n guard test fails any `.tsx` containing Slovak diacritics; all strings go through `src/i18n/sk.ts`.

### 2.3 Deferred item F2 (two metric definitions)

- Entity documents (`procurers.contract_count/total_value`, maintained by `loaders.recompute_entity_stats`): **all notice types**, `final_value` only, one count per notice per distinct ICO.
- `_firma_core_agg` (Firma "Prehľad" tab): all notice types, `final_value` only.
- `entity_profile` and all `/api/dashboard/*` aggregates: `notice_type == contract_award`, `final_value` → `estimated_value` fallback, date = `award_date` → `publication_date`.

## 3. Goals, non-goals, personas

### 3.1 Goals

1. A first-time visitor understands the Slovak procurement market in under a minute: how much, who buys, who wins, in which sectors, how concentrated, and how fresh the data is.
2. Every view is bookmarkable and shareable (filters in the URL) and every number is one click away from the underlying contracts.
3. Consistent numbers: one metric definition (§4) used by every widget, stated on the page.
4. Operators see pipeline health, API performance and data freshness in Grafana with alerts, from files in this repo.

### 3.2 Non-goals

- No rewrite of stored entity stats (F2 is sidestepped by computing at query time; a recompute is a separate decision).
- No per-user saved dashboards, no dashboard builder, no PDF export.
- No cross-source canonical de-duplication in the aggregates in this iteration (§4.4 explains the consequence and the follow-up).
- No deployment of monitoring to the cluster; only a documented path (§8.6).
- No new MCP tools (the MCP surface can expose the same services later; out of scope).

### 3.3 Personas and the questions each dashboard answers

| Persona | Needs | Dashboard |
| ------- | ----- | --------- |
| Novinár / analytik (journalist, researcher) | "How much was spent on roads in 2024, who got it, is one firm dominating?" | Prehľad trhu, Koncentrácia, CPV |
| Dodávateľ (supplier scouting a market) | "Which authorities buy IT services, how big are the contracts, who are my competitors?" | CPV (filtered), Koncentrácia (procurer dimension), drill-down list |
| Watchdog / NGO | "Where is concentration abnormally high; did it change year on year?" | Koncentrácia with date comparison, Firma workspace |
| Vývojár / operátor | "Is the data complete and fresh, which source is lagging, is the API slow?" | Pokrytie dát (SPA) + Grafana dashboards (Part B) |

## 4. Metric definitions (glossary)

All product dashboards use **definition D1**, computed at query time from `notices`. Nothing is rewritten in Mongo.

| Term | Definition (D1) | Fields |
| ---- | --------------- | ------ |
| **Zákazka (contract)** | One notice with `notice_type == "contract_award"`. Counted once per notice regardless of the number of award lines. | `notice_type` |
| **Hodnota (value)** | `coalesce(final_value, estimated_value, 0)` in EUR. | `final_value`, `estimated_value` |
| **Dátum (date)** | `coalesce(award_date, publication_date)`; ISO `YYYY-MM-DD` strings compared lexicographically. | `award_date`, `publication_date` |
| **Obstarávateľ (procurer)** | `procurer.ico`; notices without an ICO are counted in totals but excluded from per-procurer rankings. | `procurer.ico`, `procurer.name` |
| **Dodávateľ (supplier)** | Each *distinct* `awards[].supplier.ico` of a notice (`$setUnion`, not `$unwind`). The full notice value is attributed to each distinct supplier of that notice (same rule as `loaders._entity_stats_pipeline`); multi-supplier awards are rare and this keeps "top suppliers" consistent with the Firma pages. Notices without any supplier ICO are excluded from supplier rankings and concentration. | `awards.supplier.ico`, `awards.supplier.name` |
| **CPV divízia** | First two digits of `cpv_code` normalised by `uvo_core.domain.cpv.cpv_prefix` (`"45..."` → `"45000000"`); label from `cpv_labels.json` (`label_sk`), fallback to the code. `cpv_code` missing → bucket `"00000000"` ("Bez CPV"). | `cpv_code` |
| **Podiel (share)** | `entity_value / total_value_of_filtered_set * 100`, rounded to 1 decimal. | — |
| **HHI** | Herfindahl–Hirschman index over value shares of *all* entities in the filtered set: `HHI = Σ (share_i%)² = 10 000 · Σv_i² / (Σv_i)²`, range 0–10 000. Bands shown as orientation only: `< 1500` nízka, `1500–2500` stredná, `> 2500` vysoká. Entities with value 0 are ignored. | derived |
| **CR4 / CR10** | Sum of the top-4 / top-10 shares, in %. | derived |
| **Priemerná hodnota** | `total_value / contract_count` (contracts with value 0 included — stated in the tooltip; a `median` is not computed in v1). | derived |
| **Obdobie** | `[date_from, date_to]` inclusive. Default: 1 January of (current year − 4) to today. Previous period for deltas: same length immediately before `date_from`. | — |
| **Zdroj (source)** | `source ∈ {vestnik, crz, ted, uvo, itms}`. `uvo` is legacy (no running extractor). | `source` |
| **Čerstvosť (freshness)** | Age of `max(ingested_at)` per source (ISO string). Status: `healthy ≤ 24 h`, `warning ≤ 48 h`, `stale > 48 h`, `legacy` for `uvo`, `unknown` when empty. Same thresholds as `routers/ingestion.py`. | `ingested_at` |

### 4.1 Why D1

- It is what `entity_profile`, every existing `/api/dashboard/*` aggregate and `_schema.contract_value/contract_date` already use, so the SPA's contract rows and the dashboards agree.
- `contract_award` is the only notice type that represents money actually awarded; `contract_notice` is an intent and `prior_information` a plan. Mixing them (the entity-doc definition) double counts the same procurement.
- The `estimated_value` fallback keeps CRZ/ITMS records (which often lack `final_value`) in the totals; the UI labels the KPI "vrátane odhadovaných hodnôt".

### 4.2 Where D1 is *not* used (and what the user sees)

- Entity list sorting (`/api/firmy`, `/api/suppliers`, `/api/procurers`) and the Firma "Prehľad" KPI cards use the entity-doc / `_firma_core_agg` definition. The Firma page will show slightly different totals than a dashboard filtered to that ICO. Mitigation in this iteration: the Firma workspace gets a link "Zobraziť v analytike" and the dashboards label their definition; the follow-up (not in this plan) is to switch `_firma_core_agg` to D1 and recompute entity stats with D1, which is the actual F2 product decision. **Recommendation recorded: adopt D1 everywhere.**

### 4.3 Validation rules

- `date_from ≤ date_to`; span ≤ 15 years; dates ISO `YYYY-MM-DD`; otherwise 422.
- `cpv`: 2–8 digits; matched as anchored prefix on `cpv_code` (`{"$regex": "^45"}`, index-usable).
- `source`: enum above; `procurer_ico`/`supplier_ico`: 1–12 characters, digits only.
- `n` (top-N): 1–50; `granularity ∈ {month, quarter, year}`.

### 4.4 Known limitation: cross-source duplicates

The same award can exist as a vestník notice and a CRZ contract; `canonical_id` links them but is only set for a subset. D1 counts **source notices**. Consequence: totals can be inflated for procurements present in several sources. Mitigation: the `source` filter lets a user restrict to one source; the Pokrytie dashboard shows how many notices carry a `canonical_id`. Follow-up (needs P4/P6 from the refactor plan first): `dedupe=canonical` query flag grouping by `coalesce(canonical_id, _id)`.

## 5. Dashboards (Part A)

Route base: `/analytika`. Four pages sharing `AnalyticsLayout` (title, definition hint, `AnalyticsFilterBar`, tab nav). `/` redirects to `/analytika/prehlad`; `/cpv-trends` redirects to `/analytika/cpv`. `OverviewPage` and `CpvTrendsPage` are removed (their API endpoints stay).

### 5.1 Shared filter bar (`AnalyticsFilterBar`)

| Control | URL param | Default | Widget |
| ------- | --------- | ------- | ------ |
| Obdobie | `date_from`, `date_to` | `{Y-4}-01-01` … today | Two date inputs + presets: *Tento rok*, *Minulý rok*, *Posledných 5 rokov*, *Všetko (od 2014)* |
| CPV | `cpv` | — | Text input (prefix) with a datalist of divisions (label + code) |
| Zdroj | `source` | — (all) | Select |
| Obstarávateľ | `procurer_ico` | — | `EntityAutocomplete` (role procurer); chip with name |
| Dodávateľ | `supplier_ico` | — | `EntityAutocomplete` (role supplier); chip with name |
| — | *(reset)* | — | "Zrušiť filtre"; "Kopírovať odkaz" copies the current URL |

Rules: all state in URL via `useAnalyticsFilters` (thin wrapper on `useSearchParams`; defaults are *not* written to the URL so `/analytika/prehlad` stays short). Changing a filter does `replace: false` (back button works). The same param names are accepted by `/zakazky` so drill-down is a pure param copy.

### 5.2 Prehľad trhu (`/analytika/prehlad`)

Questions: how much, how many, trend, who buys, who wins.

| # | Widget | Type | Data | Drill-down |
| - | ------ | ---- | ---- | ---------- |
| 1 | KPI row: Celková hodnota, Počet zákaziek, Priemerná hodnota, Počet obstarávateľov, Počet dodávateľov | `KpiCard` with delta vs previous period | `/summary` | KPI click → `/zakazky?{filters}` |
| 2 | Objem a počet v čase | Composed chart: bars = value, line = count (secondary axis); granularity auto (`month` if span ≤ 3 y else `year`), override select | `/timeseries` | Bar click → `/zakazky?{filters, date_from/date_to = bucket}` |
| 3 | Top 10 obstarávateľov | Horizontal bar, label = name, value + share in tooltip; toggle metric value/count | `/top?dimension=procurer` | Bar click → `/zakazky?{filters, procurer_ico}`; name link → `/firma/:ico` |
| 4 | Top 10 dodávateľov | same | `/top?dimension=supplier` | same with `supplier_ico` |
| 5 | Posledné zákazky | existing table | `/api/contracts?{filters}&limit=8` | row → `/zakazky?...&selected=id` |

### 5.3 Koncentrácia trhu (`/analytika/koncentracia`)

Questions: is the filtered market dominated by few suppliers (or few buyers)?

| # | Widget | Type | Data |
| - | ------ | ---- | ---- |
| 1 | Dimension toggle: Dodávatelia / Obstarávatelia (URL `dimension`) | segmented control | — |
| 2 | KPI: HHI (+ band chip, tooltip explaining the bands), CR4, CR10, Počet subjektov | `KpiCard` | `/concentration` |
| 3 | Podiely top 10 + "Ostatní" | Horizontal stacked 100 % bar (one bar) + table (name, value, share, cumulative share) | `/concentration.top` |
| 4 | Vývoj HHI po rokoch | Line chart (one `/concentration` call per year in range, max 15, run in parallel with `useQueries`) | `/concentration` with per-year dates |
| 5 | Hint | "Index > 2500 je orientačne vysoká koncentrácia; porovnajte s inými CPV alebo obdobím." | — |

Drill-down: table row → `/firma/:ico` and `/zakazky?{filters, supplier_ico|procurer_ico}`.

### 5.4 Sektory CPV (`/analytika/cpv`)

Questions: which sectors get the money, how did the top sectors move over time?

| # | Widget | Type | Data |
| - | ------ | ---- | ---- |
| 1 | Podiel divízií (top 10 + Ostatné) | Horizontal bar list with share bars (evolves `CpvTrendsPage`) | `/cpv?level=division` |
| 2 | Vývoj top 5 divízií | Stacked bars per period (`/timeseries?split_by=cpv_division&top=5`) | `/timeseries` |
| 3 | Tabuľka divízií | sortable table: kód, názov, hodnota, počet, podiel | `/cpv` |

Drill-down: division → sets `cpv=NN` in the filter bar (stays on the page, now showing groups via `level=group`) and "Zobraziť zákazky" → `/zakazky?cpv=NN...`.

### 5.5 Pokrytie dát (`/analytika/pokrytie`)

Questions: which sources are in, how fresh, how complete. Public (no ops token), aggregate numbers only.

| # | Widget | Type | Data |
| - | ------ | ---- | ---- |
| 1 | Source cards: názov, počet oznámení, z toho zákaziek, posledná aktualizácia (relative via `formatAge`), status chip | cards | `/coverage.sources` |
| 2 | Oznámenia podľa mesiaca a zdroja (24 mesiacov) | stacked bars by source | `/coverage.monthly` |
| 3 | Kvalita údajov per zdroj | small table: % s hodnotou, % s CPV, % s IČO dodávateľa, % s IČO obstarávateľa | `/coverage.sources[].quality` |
| 4 | Prepojenie zdrojov | KPI: notices s `canonical_id`, počet skupín | `/coverage.canonical` |

The filter bar is hidden on this page (coverage ignores filters) and a note says so.

### 5.6 Entity drill-down

The existing Firma workspace (`/firma/:ico`) is the per-procurer/supplier dashboard. This iteration adds only:

- a "Koncentrácia" card on `FirmaPrehladTab` for procurers (HHI/CR4 of their suppliers) using `/concentration?procurer_ico=…&dimension=supplier`, and
- a "Zobraziť v analytike" link that opens `/analytika/prehlad?procurer_ico=…` (or `supplier_ico`).

### 5.7 UX requirements (apply to every widget)

- **States**: `ChartCard` renders skeleton while loading, `EmptyState` ("Žiadne zákazky pre zvolené filtre" + action "Rozšíriť obdobie" which sets the 5-year default) when `items`/`points` are empty, error state with message and "Skúsiť znova" (`refetch`). While refetching with `placeholderData`, the card shows a subtle "Aktualizujem…" badge instead of flashing.
- **Accessibility**: each chart is a `<figure>` with `<figcaption>` (title + effective period), the SVG container has `role="img"` and an `aria-label` sentence summarising the data (e.g. "Objem podľa roka, 2020 až 2024, najvyšší 2023: 4,2 mld. €"), and every chart has a "Zobraziť ako tabuľku" toggle that renders the same series as a `<table>` (keyboard and screen-reader path). Colours come from one 10-colour palette with ≥ 3:1 contrast against the card background; categorical series are also labelled directly, never colour-only. Focusable bars/rows for drill-down (`tabIndex=0`, Enter/Space).
- **Formatting**: `formatCurrency` (sk-SK, EUR, 0 decimals), compact axis via `formatMillions` ("1,2 M €"), new `formatPercent` (1 decimal, `%` with narrow no-break space), dates via `formatDate`. All strings in `sk.ts` under a new `analytics` section.
- **CSV export**: every `ChartCard` has "Exportovať CSV" which serialises the widget's current dataset client-side (`src/lib/csv.ts`: UTF-8 BOM, `;` delimiter, decimal comma, CRLF, header row in Slovak, filename `uvo-<view>-<date_from>_<date_to>.csv`). Server-side export is not needed: every dashboard dataset is ≤ a few hundred rows. The contract list keeps its own pagination; "Exportovať zákazky" is out of scope.
- **Performance**: TanStack Query `staleTime` 15 min for analytics keys (matches server TTL), `placeholderData: keepPreviousData` on filter change, queries keyed by the *effective* filters (defaults applied) so `/analytika/prehlad` and `/analytika/prehlad?date_from=2022-01-01&date_to=<today>` share cache entries only when identical.

## 6. API contract (`/api/analytics`)

Router: `src/uvo_api/routers/analytics.py`, prefix `/api/analytics`, tag `analytics`, GET only, no auth, CORS as the rest of `/api`. Routers call `uvo_core.services.analytics` functions directly (no string dispatch), which call a new `DashboardAnalytics` port.

### 6.1 Common query parameters

`date_from`, `date_to`, `cpv`, `source`, `procurer_ico`, `supplier_ico` — semantics and validation in §4/§4.3. Every response carries:

```json
"meta": {
  "definition": "D1",
  "filters": {"date_from": "2022-01-01", "date_to": "2026-10-19", "cpv": null, "source": null,
              "procurer_ico": null, "supplier_ico": null},
  "generated_at": "2026-10-19T10:00:00Z"
}
```

Errors: 422 (validation, FastAPI default body), 503 via `BackendUnavailable` when Mongo is down, 504 when the aggregate exceeds `maxTimeMS` (mapped from `pymongo.errors.ExecutionTimeout` in the router to a JSON `{"detail": "analytics_timeout"}`).

### 6.2 Endpoints

| Endpoint | Extra params | Response |
| -------- | ------------ | -------- |
| `GET /summary` | — | `{meta, current: Period, previous: Period \| null, deltas: {contract_count_pct, total_value_pct, avg_value_pct, procurer_count_pct, supplier_count_pct}}` where `Period = {date_from, date_to, contract_count:int, total_value:float, avg_value:float, procurer_count:int, supplier_count:int}`. `previous` is `null` when the previous window starts before 1993. Deltas are `null` when the previous value is 0. |
| `GET /timeseries` | `granularity=month\|quarter\|year` (default `month`), `split_by=source\|cpv_division` (optional), `top` (1–10, default 5, only with `split_by`) | `{meta, granularity, points: [{period, contract_count, total_value, avg_value}], series: [{key, label, points:[...]}] \| null}`. `period` is `"2024-03"`, `"2024-Q1"` or `"2024"`. Points are zero-filled over the range. With `split_by`, `series` has the top-N keys by value plus `{"key": "other", "label": "Ostatné"}`; `points` stays the total. |
| `GET /top` | `dimension=procurer\|supplier\|cpv_division` (required), `metric=total_value\|contract_count` (default `total_value`), `n` (1–50, default 10) | `{meta, dimension, metric, total: {total_value, contract_count}, items: [{key, label, ico, total_value, contract_count, share_pct}], other: {total_value, contract_count, share_pct}}`. `ico` is `null` for `cpv_division`; `key` is the ICO or the 8-digit CPV prefix. |
| `GET /concentration` | `dimension=supplier\|procurer` (default `supplier`) | `{meta, dimension, hhi: float, hhi_band: "low"\|"moderate"\|"high", cr4_pct, cr10_pct, entity_count, total_value, top: [{ico, name, total_value, share_pct, cumulative_pct}]}` (top 10). `hhi` is `0` and `hhi_band` `"low"` when `entity_count == 0`; the SPA shows the empty state in that case. |
| `GET /cpv` | `level=division\|group` (default `division`) | `{meta, level, total_value, contract_count, items: [{cpv_code, prefix, label_sk, total_value, contract_count, share_pct}]}` sorted by value desc, all buckets (≤ 45 divisions; groups fall back to the code as label when no label exists). |
| `GET /coverage` | *(ignores common filters)* | `{generated_at, sources: [{source, notices_total, contract_awards, last_publication_date, last_ingested_at, age_seconds, status, expected_cadence_seconds \| null, quality: {with_value_pct, with_cpv_pct, with_supplier_ico_pct, with_procurer_ico_pct}}], monthly: [{period, vestnik, crz, ted, uvo, itms}] (last 24 months by publication month, all notice types), canonical: {notices_with_canonical_id, match_groups}}` |

Pydantic response models live in `uvo_api/models.py` (section `# --- Analytics dashboards ---`). TypeScript mirrors in `src/api/types.ts` (section `// ── Analytics ──`). The JSON above is the contract the frontend builds against with fixtures before the backend lands.

### 6.3 `/api/contracts` additions (drill-down target)

- New optional `source` param. On the no-text path it joins `_find_filter`; on the `$search` path it is applied as a `$match` *after* `$search` (same technique as the value filter) because `source` is not a token in the Atlas Search index and changing the index mapping would trigger a rebuild (`CLAUDE.md`, "Data / search gotchas").
- `date_from`/`date_to` keep filtering on `publication_date` (as today). The dashboards filter on D1 date; the drill-down list may therefore differ by the notices whose `award_date` and `publication_date` fall in different buckets. Documented in the UI hint ("Zoznam je filtrovaný podľa dátumu zverejnenia"). Changing the list filter to D1 date is not done here because it would move the hot text-search path off its indexed `publication_date` range.

## 7. Data, index, caching and performance design

### 7.1 Core design

```
uvo_api/routers/analytics.py      ──► uvo_core/services/analytics.py  ──► ports.DashboardAnalytics
         (shape + validate)                (typed use-cases, defaults)        │
                                                                              ├─ adapters/mongo/dashboards.py (MongoDashboardAnalytics,
                                                                              │    pipeline builders, async_ttl_cache)
                                                                              └─ testing.InMemoryDashboardAnalytics (fake for tests)
uvo_core/domain/analytics.py: DashboardFilter (frozen dataclass), D1 constants, period helpers, hhi()/bands
```

- `DashboardFilter(date_from, date_to, cpv, source, procurer_ico, supplier_ico)` is hashable and is the cache key.
- Pipeline builders are pure functions (`build_summary_pipeline(f)`, `build_timeseries_pipeline(f, granularity, split_by, top)`, `build_top_pipeline(f, dimension, metric, n)`, `build_concentration_pipeline(f, dimension)`, `build_cpv_pipeline(f, level)`, `build_coverage_pipelines()`), unit-tested by asserting stage shapes (as `tests/core/test_dashboard_builders.py` does today).
- Shaping functions (`shape_summary`, `shape_timeseries`, …) are pure and tested with fixture rows.

### 7.2 Index-friendly match stage

```python
{"notice_type": "contract_award",
 "$or": [{"award_date": {"$gte": f.date_from, "$lte": f.date_to}},
         {"award_date": None, "publication_date": {"$gte": f.date_from, "$lte": f.date_to}}],
 # optional:
 "cpv_code": {"$regex": "^45"}, "source": "vestnik", "procurer.ico": "...", "awards.supplier.ico": "..."}
```

Same shape as `build_monthly_buckets_pipeline` (proven index-usable). New indexes in `loaders.ensure_indexes` (idempotent, created by the ingestor at startup and by the legacy pipeline; the API never creates B-tree indexes):

| Index | Why |
| ----- | --- |
| `{notice_type: 1, award_date: -1}` `notice_type_award_date_desc` | First `$or` branch; today only `publication_date` has a compound. |
| `{source: 1, notice_type: 1, publication_date: -1}` `source_notice_type_publication_date_desc` | `source` filter and the coverage per-source groups. |

Existing `{procurer.ico, notice_type}`, `{awards.supplier.ico, notice_type}` and `cpv_code` cover the entity and CPV filters. All aggregates run with `allowDiskUse=True`, `maxTimeMS=15_000`.

### 7.3 Caching

| Aggregate | TTL | maxsize | Invalidation |
| --------- | --- | ------- | ------------ |
| summary, timeseries, top, concentration, cpv | 15 min | 512 (keyed by filter tuple + params) | `notices:written` (`clear_data_caches`) + TTL |
| coverage | 15 min | 1 | same |

Rationale: the corpus changes hourly at most; the invalidation hook already clears every data-dependent cache (debounced to once per 60 s). In-flight coalescing in `async_ttl_cache` protects against a thundering herd on the default filters. Optional warm-up: the API lifespan schedules `warm_default_dashboards()` (summary/timeseries/top/cpv/coverage for the default filter) 5 s after startup, best effort, so the landing page never pays the cold cost; it is also re-run by the invalidation callback (debounced). `docs/architecture/caching.md` gets a new row block.

### 7.4 Performance budgets

| Path | Budget | How verified |
| ---- | ------ | ------------ |
| Warm (cached) analytics endpoint | p95 ≤ 50 ms server time | API histogram `uvo_api_http_request_duration_seconds{route="/api/analytics/..."}` |
| Cold full-range aggregate, prod-size corpus | p95 ≤ 2 s, hard cap 15 s (`maxTimeMS`) | `explain()` in a one-off script; `uvo_cached_call_duration_seconds{cache="dashboards.*"}` histogram after deploy |
| Landing page `/analytika/prehlad` | 4 requests (summary, timeseries, top×2) + recent; ≤ 1.5 s to first chart on warm cache | Lighthouse/manual |
| HHI year series | ≤ 15 parallel requests, each cached independently | — |

Risk: the prod corpus size is not known precisely here (CLAUDE.md implies millions of notices). The cold budget must be measured in WS-A on a prod-size dump before the frontend defaults to "Všetko (od 2014)".

## 8. Monitoring (Part B)

### 8.1 Metric additions

All names are the contract between code (WS-C) and dashboards/alerts (WS-D).

**API — `src/uvo_api/metrics.py`** (default `prometheus_client` registry; `GET /metrics` outside `/api`, so nginx never proxies it; in k8s it is reachable only in-cluster):

| Metric | Type | Labels | Source |
| ------ | ---- | ------ | ------ |
| `uvo_api_http_requests_total` | counter | `method, route, status` | ASGI middleware; `route` is the matched template (`/api/analytics/top`), never the raw path (bounded cardinality); unmatched → `"unmatched"` |
| `uvo_api_http_request_duration_seconds` | histogram (buckets 0.01…10) | `method, route` | same |
| `uvo_api_http_requests_in_progress` | gauge | — | same |
| `uvo_ready` | gauge 0/1 | `service="uvo-api"` | background task every 30 s: `mongo_ready` + `SearchIndexProbe.ready` |
| `uvo_source_notices_total` | gauge | `source` | background task every 300 s via `uvo_pipeline.health.collect(db)` |
| `uvo_source_last_ingested_timestamp_seconds` | gauge | `source` | same (0 when none) |
| `uvo_source_ingested_24h` | gauge | `source` | same |
| `uvo_build_info` | gauge 1 | `version, git_sha` | `GIT_SHA` env (compose/k8s), package version |

**Core — `src/uvo_core/observability.py`** (used by `uvo_core/cache.py`; `prometheus_client` is already a core dependency and import-linter allows it):

| Metric | Type | Labels |
| ------ | ---- | ------ |
| `uvo_cache_requests_total` | counter | `cache, result ∈ {hit, miss, inflight}` |
| `uvo_cached_call_duration_seconds` | histogram | `cache` — time of the underlying call on a miss, which instruments every aggregate without touching adapters |

`async_ttl_cache` gets an optional `name=` (default `fn.__module__.split('.')[-1] + '.' + fn.__name__`).

**Workers — `src/uvo_workers/metrics.py`** additions to `WorkerMetricsCollector`:

| Metric | Type | From snapshot key |
| ------ | ---- | ----------------- |
| `uvo_worker_cycles_completed_total{component}` | counter | `cycles_completed` |
| `uvo_worker_cycles_skipped_locked_total{component}` | counter | `cycles_skipped_locked` |
| `uvo_worker_dedup_runs_total{component}` | counter | `dedup_runs` |
| `uvo_worker_last_error{component}` | gauge 0/1 | `last_error is not None` |
| `uvo_worker_start_timestamp_seconds{component}` | gauge | `started_at_ts` (set by `WorkerContext.__init__`) |
| `uvo_worker_info{component, source, instance_id}` | gauge 1 | — |

Existing families are unchanged (names are consumed by `db-monitor` docs). Only keys present in the snapshot are emitted, so an extractor never reports `dedup_runs`.

**MCP — `src/uvo_mcp/server.py`**: `custom_route("/metrics")` rendering the default registry (process metrics, cache metrics, `uvo_ready{service="uvo-mcp"}` refreshed by the same 30 s pattern). Tool-call counters are a follow-up.

### 8.2 Prometheus (`monitoring/prometheus/prometheus.yml`)

Scrape interval 30 s. Jobs: `uvo-api` (`api:8001`), `uvo-mcp` (`mcp-server:8000`), `uvo-workers` (`extractor-vestnik:8091`, `extractor-crz:8092`, `extractor-ted:8093`, `extractor-itms:8094`, `ingestor:8095`, `dedup-worker:8096`) with `component` label relabelled from the target name; `prometheus` self-scrape. Rule file `rules/uvo-alerts.yml`. No remote write, no Alertmanager in the dev profile (alerts visible in the Prometheus UI and on the Grafana dashboards' alert list panel).

### 8.3 Alert rules (`monitoring/prometheus/rules/uvo-alerts.yml`)

| Alert | Expression (sketch) | For | Severity |
| ----- | ------------------- | --- | -------- |
| `UvoWorkerDown` | `up{job="uvo-workers"} == 0` | 5m | critical |
| `UvoApiDown` / `UvoMcpDown` | `up{job="uvo-api"} == 0` | 5m | critical |
| `UvoApiNotReady` / `UvoMcpNotReady` | `uvo_ready == 0` | 5m | critical |
| `UvoStreamLagHigh` | `max by (stream) (uvo_worker_stream_lag) > 10000` | 15m | warning |
| `UvoStreamPendingStuck` | `max by (stream) (uvo_worker_stream_pending) > 500` | 30m | warning |
| `UvoDeadLettersGrowing` | `increase(uvo_worker_dead_letter_length[1h]) > 0` | 0m | warning; `> 100` critical |
| `UvoExtractorStalled` | `time() - uvo_worker_last_success_timestamp_seconds{component=~"extractor-(vestnik\|crz\|itms)"} > 3*3600 and uvo_worker_last_success_timestamp_seconds > 0`; TED variant with `> 3*21600` | 10m | warning |
| `UvoExtractorNeverSucceeded` | `uvo_worker_last_success_timestamp_seconds == 0 and time() - uvo_worker_start_timestamp_seconds > 1800` | 0m | warning |
| `UvoWorkerErrorPersisting` | `uvo_worker_last_error == 1` | 30m | warning |
| `UvoWorkerRedisDisconnected` | `uvo_worker_redis_connected == 0` | 5m | critical |
| `UvoSourceStale` | `time() - uvo_source_last_ingested_timestamp_seconds{source!="uvo"} > 172800` | 0m | warning |
| `UvoApiErrorRate` | `sum(rate(uvo_api_http_requests_total{status=~"5.."}[10m])) / sum(rate(uvo_api_http_requests_total[10m])) > 0.05 and sum(rate(uvo_api_http_requests_total[10m])) > 0.1` | 10m | warning |
| `UvoApiSlow` | `histogram_quantile(0.95, sum by (le) (rate(uvo_api_http_request_duration_seconds_bucket{route=~"/api/(analytics\|contracts\|search).*"}[10m]))) > 2` | 10m | warning |
| `UvoCacheHitRateLow` | `sum(rate(uvo_cache_requests_total{result="hit"}[30m])) / sum(rate(uvo_cache_requests_total[30m])) < 0.5` with traffic guard | 30m | info |

Thresholds are starting points and are stated in the rule `description` so they can be tuned after a week of data. Every rule has a `runbook` annotation pointing to `monitoring/README.md#alerts`.

### 8.4 Grafana dashboards (`monitoring/grafana/dashboards/*.json`)

Provisioned from file (`monitoring/grafana/provisioning/dashboards/dashboards.yml`, folder "UVO"), datasource `prometheus` (uid `prometheus`, provisioned). Dashboards are plain JSON with stable `uid`s, `schemaVersion` ≥ 39, `time: now-24h`, refresh 30 s, templating variable `component`.

| uid | Title | Rows / panels |
| --- | ----- | ------------- |
| `uvo-pipeline-health` | UVO · Pipeline health | **Streams**: lag per stream (timeseries), pending per stream, dead letters (stat + sparkline), notices written rate (`rate(uvo_worker_notices_written[5m])`). **Workers**: table of components with `up`, last success age, last error, cycles/24h, skipped-locked; Redis connected. **Alerts**: alert list panel filtered to `Uvo*`. |
| `uvo-api-performance` | UVO · API & search performance | Requests/s by route (top 10), error ratio, p50/p95/p99 latency overall and per route group (analytics, contracts, search, firma, graph), in-progress, readiness (`uvo_ready`), cache hit ratio by cache, cached-call p95 by cache (which aggregate is slow), MCP readiness and process memory. |
| `uvo-data-freshness` | UVO · Data freshness | Per-source: notices total (stat), last ingested age (stat with thresholds 24 h/48 h), ingested last 24 h (bar gauge), 7-day ingestion trend from `uvo_source_notices_total` deltas, `UvoSourceStale` alert state. |

### 8.5 Local stack — `docker compose --profile monitoring up -d`

Two services added to `docker-compose.yml` under `profiles: ["monitoring"]`:

- `prometheus` — `prom/prometheus:v2.54.1`, `127.0.0.1:9090:9090`, mounts `./monitoring/prometheus:/etc/prometheus:ro`, volume `prometheus_data`, `--storage.tsdb.retention.time=7d`.
- `grafana` — `grafana/grafana-oss:11.2.0`, `127.0.0.1:3000:3000`, env `GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-uvo_grafana_dev}` (dev default allowed by the same loopback argument as `REDIS_PASSWORD`; documented in `.env.example`), `GF_AUTH_ANONYMOUS_ENABLED=false`, `GF_USERS_ALLOW_SIGN_UP=false`, mounts `./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro` and `./monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro`, volume `grafana_data`, `depends_on: prometheus`.

Workers already serve `/metrics` on their health ports inside the compose network; nothing else is exposed. `monitoring/README.md` documents start, URLs, default login, how to add a panel, and how to run the rule tests.

### 8.6 Follow-up: consumption by `stubarag-infra` (not done here)

- The Helm chart would add `ServiceMonitor`/`PodMonitor` objects (or scrape annotations) for API, MCP and each worker, keeping the `job` and `component` label values used by the dashboards (`uvo-api`, `uvo-mcp`, `uvo-workers` + `component=extractor-vestnik` …).
- Dashboards: a `ConfigMap` with the `grafana_dashboard: "1"` label (sidecar provisioning) built from `monitoring/grafana/dashboards/*.json`; alert rules as a `PrometheusRule` built from `monitoring/prometheus/rules/uvo-alerts.yml`. A tiny `scripts/render_k8s_monitoring.sh` (kustomize `configMapGenerator`) can produce both; it is listed as optional in the plan.
- A NetworkPolicy must allow the monitoring namespace to reach `/metrics` ports; `/metrics` on the API is not under `/api`, so the public Traefik route never exposes it.

## 9. Testing strategy

| Layer | What | Where |
| ----- | ---- | ----- |
| Core unit | Pipeline builders (stage shapes, index-friendly match, `$or` date window, cpv regex anchor), shaping functions (zero-fill, quarter mapping, HHI/CR4, share rounding, other-bucket), `DashboardFilter` defaults/validation, `hhi()` against hand-computed values | `tests/core/test_dashboards_builders.py`, `test_dashboards_shaping.py`, `test_analytics_domain.py` |
| API unit | Each endpoint with `InMemoryDashboardAnalytics` (dependency override), 422 cases, 504 mapping, meta echo, `source` on `/api/contracts` (`$match` placement on the text path asserted on the pipeline) | `tests/api/test_analytics.py`, `tests/api/test_contracts_source_filter.py` |
| Observability unit | Middleware counts/labels with route template, `/metrics` renders, readiness gauge flips, cache hit/miss counters, worker collector families from snapshot, `start_timestamp` present, MCP `/metrics` | `tests/api/test_metrics.py`, `tests/core/test_observability.py`, `tests/workers/test_metrics.py` (extend), `tests/mcp/test_metrics.py` |
| Frontend unit | `useAnalyticsFilters` URL round-trip and defaults, filter bar presets, `csv.ts` (BOM, `;`, decimal comma), `ChartCard` states, drill-down link builders, table toggle renders rows, `/zakazky` accepting `date_from/date_to/source/procurer_ico`, i18n guard | `src/test/analytics*.test.tsx`, `src/test/csv.test.ts` |
| E2E (compose) | Seed ~30 notices across sources via Mongo, hit every `/api/analytics/*` endpoint and assert shapes/invariants (`sum(share_pct) ≈ 100`, totals equal `/api/contracts` count for the same filters on the no-text path), GUI route `/analytika/prehlad` serves | `tests/e2e/test_analytics.py` |
| Monitoring | `promtool check config`, `promtool check rules`, `promtool test rules` with unit cases per alert (fires / does not fire), dashboards parse as JSON with unique `uid`s and only the provisioned datasource, Grafana container smoke (`/api/health`, `/api/search?query=UVO` returns 3) | `.github/workflows/ci.yml` job `monitoring`, `monitoring/prometheus/rules/tests/` |
| Performance | One-off `scripts/bench_analytics.py` printing `explain` summary and timings for the default and the all-time filter on a prod-size dump | WS-A acceptance |

## 10. Rollout and risks

Order: WS-C (observability) and WS-D (monitoring files) are independent and can merge first; WS-A (backend) is additive and merges next; WS-B (frontend) is built against fixtures in parallel and merges after WS-A (it only needs the API for E2E). Publishing is unchanged (`docker-publish.yml`); prod picks the new `sha-` tag in `stubarag-infra` when the user decides.

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Cold aggregates too slow on prod corpus | Landing page stalls after deploy or invalidation | TTL cache + in-flight coalescing; warm-up task; `maxTimeMS`; measure before enabling the "Všetko" preset; fallback is to cap the default range |
| Invalidation storms during backfills | Caches cleared every 60 s → repeated cold cost | Already debounced; warm-up re-populates default filters; if needed raise the debounce for analytics only |
| Cross-source double counting (§4.4) | Totals overstated for duplicated procurements | `source` filter, coverage page transparency, planned `dedupe=canonical` |
| Divergent Firma numbers (§4.2) | User confusion | Definition hint + link; recommended F2 decision: D1 everywhere |
| `route` label cardinality | Prometheus memory | Template routes only; unmatched collapsed |
| `/metrics` exposure | Internal topology leak | Not under `/api` (nginx does not proxy); k8s NetworkPolicy in the follow-up; no secrets in metrics |
| recharts accessibility gaps | a11y failure | Table toggle is the guaranteed path; `aria-label` summaries |
| CPV labels only at division level | Groups show raw codes | Acceptable for v1; label file can grow later |
