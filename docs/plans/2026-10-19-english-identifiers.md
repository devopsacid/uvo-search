# English identifiers — rename map (2026-10-19)

Request: "change all endpoint names to English, refactor whole code to English words, not Slovak
terms in code." Two implementers work in parallel from this file: a **backend agent** (section 3)
and a **frontend agent** (section 4). Section 2 is the shared contract — both must match it
byte for byte. Everything here was verified by grepping `main` at `293eedb`.

## 1. Scope and non-goals

**Rename (code identifiers, paths, keys):**

- `/api/firma*`, `/api/firmy` → `/api/companies*` (old paths kept as hidden aliases for one release).
- Slovak JSON keys in `/api/search/unified` (`firmy`, `zakazky`). No other `/api/firma*`/`/api/firmy`
  response key is Slovak (verified in `src/uvo_api/models.py` lines 304–383: `FirmaProfile`,
  `PartnerRow`, `CpvProfileRow`, `FirmaCard` are all English-keyed).
- SPA routes `/analytika/*`, `/firma/:ico/*`, `/firmy`, `/zakazky`, `/hladaj` → English, with
  query-preserving redirects from every old path.
- Python modules/functions/classes/variables/tests, React files/components/hooks/query keys/types,
  i18n **keys** (values untouched), test files and fixtures, monitoring expressions.

**Keep (non-goals):**

- User-visible Slovak text: every value in `src/uvo-gui-react/src/i18n/sk.ts`, `index.html` title
  ("UVO Vyhladavanie"), labels such as the autocomplete sublabel `IČO {ico}`.
- `ico` everywhere (persisted field, Atlas index, `/v1` path param, `supplier_ico`, `procurer_ico`,
  `pin_ico`).
- Source proper nouns `vestnik`, `crz`, `ted`, `itms`, `uvo`: checkpoint keys, env vars, Redis
  stream names, metric names, `sk.ts` keys `vestnik/crz/ted/itms/uvo`.
- Inbound raw payload keys of ITMS/Vestník/CRZ as **strings** (`obstaravatelSubjekt`, `zadavatel`,
  `subjekt`, `dodavatelia`, `celkovaSumaZmluvy`, `predpokladanaHodnotaZakazky`,
  `datumZverejneniaVoVestniku`, `stav`, `nazov`, `mena`, `pocetPrijatychPonuk`,
  `verejneObstaravania`, `zmluvyVerejneObstaravanie`, `hlavnyDodavatelDodavatelObstaravatel`, ITMS
  URL paths `/v2/verejneObstaravania`, `/v2/subjekty`, `/v2/dodavatelia`). Only the Python
  identifiers wrapping them change (section 3.3).
- MCP tool names, everything under `/v1` (already English; it is a separate mounted FastAPI app
  with its own OpenAPI, so `uvo_api/models.py` may reuse the names `CompanyProfile`, `CompanyCard`,
  `CompanyListResponse` that `routers/v1/models.py` also defines without schema clashes).
- Mongo/Neo4j field and collection names, Atlas Search index definitions — no data rewrite.
- Historical docs under `docs/superpowers/` and dated plan/spec files already merged
  (`docs/plans/2026-10-19-analytics-dashboards-plan.md`, `docs/specs/2026-10-19-analytics-dashboards.md`,
  `docs/architecture/ports-and-adapters-plan.md`): leave as-is.
- Slovak **data** in tests/fixtures (company names like `Doprastav`, `Stavebná firma s.r.o.`, CPV
  labels in `cpv_labels.json`, notices in `tests/fixtures/analytics_notices.json`, dedup test
  titles). Only identifiers are renamed; string literals that are test data stay.
- Behaviour. This is a pure rename: no handler logic, query, filter or UI change.

## 2. Shared contract (both agents must match exactly)

### 2.1 API paths

| Old (kept as hidden alias) | New (canonical, in OpenAPI) | Query params (unchanged) |
| --- | --- | --- |
| `GET /api/firma/{ico}` | `GET /api/companies/{ico}` | — |
| `GET /api/firma/{ico}/partneri` | `GET /api/companies/{ico}/partners` | `role`, `sort`, `limit`, `offset` |
| `GET /api/firma/{ico}/cpv-profile` | `GET /api/companies/{ico}/cpv-profile` | — |
| `GET /api/firmy` | `GET /api/companies` | `q`, `role`, `limit`, `offset` |
| `GET /api/search/unified` | unchanged path, **keys change** (2.2) | `q`, `limit` |
| `GET /api/search/entities` | unchanged | — |

Collision check (done): no existing `/api/companies*` route; `/api/{contracts,suppliers,procurers,
dashboard,analytics,graph,search,ingestion,ingestion-log,worker-status}` untouched; `/v1/companies`
lives on the mounted `/v1` sub-app, so `/api/companies` is a distinct path. OpenAPI tag:
`companies` (replaces `firma` and `firmy`).

**Aliases.** One extra `APIRouter(include_in_schema=False)` in `src/uvo_api/routers/companies.py`
registers the four old paths with `add_api_route(..., endpoint=<same function>)` so handler, models
and status codes are shared; no redirect, no extra hop. Metric label `route` keeps reporting old
templates (`/api/firma/{ico}` etc.) for alias traffic, which is how removal is decided (section 7).

### 2.2 JSON keys

| Endpoint | Old key | New key | Type |
| --- | --- | --- | --- |
| `GET /api/search/unified` | `firmy` | `companies` | `CompanyHit[]` (`ico`, `name`, `roles`, `contract_count`) |
| `GET /api/search/unified` | `zakazky` | `contracts` | `ContractHit[]` (`id`, `title`, `procurer_name`, `value`, `year`) |

`q` and all nested keys are already English and unchanged. No key change on `/api/companies*`.
The 404 detail of `/api/companies/{ico}` becomes `"Company not found"` (the GUI renders its own
`sk.company.notFound` and only inspects the status code).

**Decision: rename keys, no dual-key period, deploy API and GUI images together** (section 7).

### 2.3 SPA routes

| Old path | New path | Notes |
| --- | --- | --- |
| `/` | `/` → redirect `/analytics/overview` | index redirect |
| `/analytika` | `/analytics` → redirect `/analytics/overview` | |
| `/analytika/prehlad` | `/analytics/overview` | |
| `/analytika/koncentracia` | `/analytics/concentration` | |
| `/analytika/cpv` | `/analytics/cpv` | |
| `/analytika/pokrytie` | `/analytics/coverage` | |
| `/firma/:ico` | `/company/:ico` → redirect `/company/:ico/overview` | |
| `/firma/:ico/prehlad` | `/company/:ico/overview` | |
| `/firma/:ico/zakazky` | `/company/:ico/contracts` | |
| `/firma/:ico/siet` | `/company/:ico/network` | |
| `/firma/:ico/partneri` | `/company/:ico/partners` | |
| `/firma/:ico/cpv` | `/company/:ico/cpv` | |
| `/firmy` | `/companies` | |
| `/zakazky` | `/contracts` | `?selected=<id>` and all filter params unchanged |
| `/hladaj` | `/search` | `?q=` unchanged |
| `/about`, `/graph`, `/ingestion` | unchanged | |

**Redirects (all must preserve `location.search` and `location.hash`).** Replace the
`<Navigate to="…">` entries (which drop the query string today) with one helper
`<RedirectPreservingQuery to="/x" />` (`useLocation()`, `Navigate to={{ pathname, search, hash }} replace`)
and a param-aware variant for `:ico`.

| Old path | Redirect target |
| --- | --- |
| `/analytika` | `/analytics` |
| `/analytika/:page` (`prehlad\|koncentracia\|cpv\|pokrytie`) | `/analytics/{overview\|concentration\|cpv\|coverage}` |
| `/firma/:ico` | `/company/:ico` |
| `/firma/:ico/:tab` (`prehlad\|zakazky\|siet\|partneri\|cpv`) | `/company/:ico/{overview\|contracts\|network\|partners\|cpv}` |
| `/firmy` | `/companies` |
| `/zakazky` | `/contracts` |
| `/hladaj` | `/search` |
| `/suppliers`, `/procurers`, `/pinpoint` (existing legacy) | `/companies` |
| `/suppliers/:ico`, `/procurers/:ico` (existing legacy) | `/company/:ico` |
| `/cpv-trends` (existing legacy) | `/analytics/cpv` |

**`/search` collision — resolved.** Today `/search` is a legacy redirect to `/zakazky` (contracts
list). After the rename `/search` **is** the unified search page (old `HladajPage`); the legacy
`search → zakazky` redirect is **deleted**. Rationale: the only parameter the old `/search` ever
carried was `q`, which the unified page reads too, and its contracts group covers the old use.
No redirect chain: `/hladaj → /search` lands on the page directly.

nginx (`src/uvo-gui-react/nginx.conf`): no change needed — `location /api/` proxies by prefix and
`location /` falls back to `index.html`; no route-specific blocks exist.

### 2.4 Order of operations

Both agents may work in parallel on separate worktrees/branches. The backend branch must keep the
old alias paths and **may not** be merged before the frontend branch is ready; the frontend branch
targets the new paths and keys only. Merge both, then publish and roll out together (section 7).

## 3. Backend rename table (owner: backend agent)

Files: `src/uvo_api`, `src/uvo_core`, `src/uvo_pipeline`, `tests/` (incl. `tests/e2e`),
`scripts/`, `monitoring/`, `docker-compose.yml`, `.github/`. Nothing in `src/uvo-gui-react`.

### 3.1 Modules and routers

| Old | New | Kind | Files |
| --- | --- | --- | --- |
| `src/uvo_api/routers/firma.py` | `src/uvo_api/routers/companies.py` | module (git mv) | `routers/`, `app.py` imports |
| `router = APIRouter(prefix="/api/firma", tags=["firma"])` + `firmy_router = APIRouter(prefix="/api/firmy", tags=["firmy"])` | single `router = APIRouter(prefix="/api/companies", tags=["companies"])` with `""`, `/{ico}`, `/{ico}/partners`, `/{ico}/cpv-profile`; plus `legacy_router = APIRouter(include_in_schema=False)` (2.1) | router objects | `routers/companies.py` |
| `from uvo_api.routers.firma import firmy_router` / `app.include_router(firma.router)` / `app.include_router(firmy_router)` | `from uvo_api.routers import companies` / `app.include_router(companies.router)` / `app.include_router(companies.legacy_router)` | wiring | `src/uvo_api/app.py:23-37,175-176` |
| `get_firma_profile` | `get_company_profile` | function | `routers/companies.py` |
| `get_firma_partneri` | `get_company_partners` | function | `routers/companies.py` |
| `get_firma_cpv_profile` | `get_company_cpv_profile` | function | `routers/companies.py` |
| `list_firmy` | `list_companies` | function | `routers/companies.py` |
| `detail="Firma nenájdená"` | `detail="Company not found"` | string (API, not UI) | `routers/companies.py:67`, `tests/api/test_firma.py:219` |
| `"""Unified company profile endpoint …"""` / comments mentioning firma | reword in English | docstrings | `routers/companies.py`, `routers/search.py:179-190` |

### 3.2 Models (`src/uvo_api/models.py` lines 304–383 and `routers/search.py`)

| Old | New | Kind | Files |
| --- | --- | --- | --- |
| `FirmaStatsBlock` | `CompanyStatsBlock` | pydantic model | `models.py`, `routers/companies.py` |
| `FirmaStats` | `CompanyStats` | pydantic model | same |
| `FirmaTopContract` | `CompanyTopContract` | pydantic model | same |
| `FirmaTopCpv` | `CompanyTopCpv` | pydantic model | same |
| `FirmaProfile` | `CompanyProfile` | pydantic model | same |
| `FirmaCard` | `CompanyCard` | pydantic model | same |
| `FirmaListResponse` | `CompanyListResponse` | pydantic model | same |
| `FirmaHit` | `CompanyHit` | pydantic model | `routers/search.py` |
| `ZakazkaHit` | `ContractHit` | pydantic model | `routers/search.py` |
| `UnifiedSearchResponse.firmy` | `.companies` | **JSON key** (2.2) | `routers/search.py` |
| `UnifiedSearchResponse.zakazky` | `.contracts` | **JSON key** (2.2) | `routers/search.py` |
| `_to_firma_hit` | `_to_company_hit` | function | `routers/search.py` |
| `_contract_to_zakazka` | `_to_contract_hit` | function | `routers/search.py` |
| `_merge_firmy` | `_merge_companies` | function | `routers/search.py` |
| `_merge_firmy_with_vector` | `_merge_companies_with_vector` | function | `routers/search.py` |
| locals `firmy`, `zakazky` in `unified_search` | `companies`, `contracts` | variables | `routers/search.py` |

### 3.3 Core and pipeline

| Old | New | Kind | Files |
| --- | --- | --- | --- |
| `_firma_core_agg` | `_company_core_agg` | function (keep leading underscore) | `src/uvo_core/adapters/mongo/analytics.py:66,581,600`; `routers/companies.py`; `tests/api/test_firma*.py`; `tests/core/test_cache_invalidation.py` |
| `_firma_partners_agg` | `_company_partners_agg` | function | `analytics.py:139,582,603`; `routers/companies.py`; `tests/api/test_firma_extensions.py`; `tests/core/test_analytics_queries.py`, `tests/core/test_cache_invalidation.py` |
| comments "firma helpers", "firma top contracts, unified-search zakazky", "Dashboard / firma query paths", "/api firma + search routers" | English wording ("company …") | comments | `analytics.py:3`, `procurements.py:39-40`, `loaders.py:63`, `domain/companies.py:3` |
| `_STAV_TO_STATUS` | `_RAW_STATUS_TO_STATUS` | constant | `src/uvo_pipeline/transformers/itms.py:26,25(use)` |
| local `stav = raw.get("stav", "")` | `raw_status = raw.get("stav", "")` | variable (string key stays) | `transformers/itms.py` |

Other `uvo_pipeline` hits (`extractors/itms.py`, `transformers/itms.py`, `scripts/enrich_itms_procurers.py`)
are raw payload keys or ITMS URL paths inside string literals — keep.

### 3.4 Tests

| Old | New | Kind | Files |
| --- | --- | --- | --- |
| `tests/api/test_firma.py` | `tests/api/test_companies.py` | file (git mv) | |
| `tests/api/test_firma_extensions.py` | `tests/api/test_companies_extensions.py` | file (git mv) | |
| request paths `/api/firma/…`, `/api/firmy` in those two files and `tests/api/test_unified_search.py` | `/api/companies/…` | strings | plus **one new test per alias path** asserting 200 and identical body to the canonical path, and one asserting the aliases are absent from `/openapi.json` |
| `_firmy_patches` | `_companies_patches` | fixture helper | `test_companies_extensions.py` |
| `test_firma_*`, `test_firmy_*`, `test_partneri_*` | `test_company_*`, `test_companies_*`, `test_partners_*` | test names | `test_companies*.py` |
| `test_unified_firmy_shape`, `test_unified_zakazky_shape`, `test_unified_firmy_deduplication`, `test_unified_ico_query_returns_only_firmy`, `test_unified_contract_branch_failure_keeps_firmy_and_logs` | `…companies_shape`, `…contracts_shape`, `…companies_deduplication`, `…returns_only_companies`, `…keeps_companies_and_logs` | test names | `tests/api/test_unified_search.py` |
| `["firmy"]` / `["zakazky"]` assertions | `["companies"]` / `["contracts"]` | JSON keys | `tests/api/test_unified_search.py` |
| dummy route `/api/firma/{ico}` + `async def firma` in the metrics fixture app | `/api/companies/{ico}`, `async def company` | fixture | `tests/api/test_metrics.py:28-48` |
| `test_transform_status_unknown_for_unrecognised_stav` | `…_for_unrecognised_raw_status` | test name | `tests/pipeline/transformers/test_itms.py` |
| `test_transform_award_uses_celkova_suma_zmluvy`, `test_new_shape_procurer_*_zadavatel_ico_*` | keep (they name the raw payload key) | — | |
| `ANALYTICS_PAGES = ["prehlad", "koncentracia", "cpv", "pokrytie"]`, `f"{GUI}/analytika/{page}"`, `f"{GUI}/analytika"` | `["overview", "concentration", "cpv", "coverage"]`, `/analytics/{page}`, `/analytics` | e2e | `tests/e2e/test_analytics.py:53,570,577` |
| docstring "non-empty /zakazky list" | "/contracts" | e2e comment | `tests/e2e/test_analytics.py:379` |
| comment "UVO Vyhladavanie" | keep (quotes the HTML title) | — | `tests/e2e/test_docker_compose.py:54` |

### 3.5 Monitoring / infra

| Old | New | Kind | Files |
| --- | --- | --- | --- |
| `route=~\"/api/firma.*\"` | `route=~\"/api/(companies\|firma\|firmy).*\"` (drop `firma\|firmy` when aliases go) | PromQL | `monitoring/grafana/dashboards/uvo-api-performance.json:1027` |
| `"legendFormat": "firma"` | `"companies"` | dashboard | same file `:1028` |
| `route=~"/api/(analytics\|contracts\|search).*"` | unchanged (never covered firma; widening is out of scope) | alert | `monitoring/prometheus/rules/uvo-alerts.yml:165` |
| `docker-compose.yml`, `.github/workflows/*`, `deploy/` | no Slovak path references (verified); the `/api/search?type=dash-db` hit in `ci.yml:232` is Grafana's own API | — | |

## 4. Frontend rename table (owner: frontend agent)

Files: `src/uvo-gui-react` only (`src/**`, `README.md`; never `dist/`).

### 4.1 Routes, pages, components

| Old | New | Kind | Files |
| --- | --- | --- | --- |
| route tree in `src/router.tsx` | per 2.3, with `RedirectPreservingQuery` helper | routes | `src/router.tsx` |
| `SupplierRedirect`, `ProcurerRedirect` (`/firma/${ico}`) | `CompanyRedirect` → `/company/${ico}` (query-preserving) | components | `src/router.tsx` |
| `pages/ZakazkyPage.tsx` / `ZakazkyPage` | `pages/ContractsPage.tsx` / `ContractsPage` | file + component | router, tests (`states`, `urlFilters`, `autocomplete`, `entityLinks`, `zakazkyFilters`), `components/layout/Sidebar.tsx` comment |
| `pages/HladajPage.tsx` / `HladajPage` | `pages/SearchPage.tsx` / `SearchPage` | file + component | router |
| `pages/FirmaPage.tsx` / `FirmaPage` | `pages/CompanyPage.tsx` / `CompanyPage` | file + component | router, `api/queries` comment |
| `pages/FirmyPage.tsx` / `FirmyPage` | `pages/CompaniesPage.tsx` / `CompaniesPage` | file + component | router |
| `pages/firma/` | `pages/company/` | directory | router |
| `FirmaPrehladTab` | `CompanyOverviewTab` | file + component | `pages/company/`, router, `test/firma.test.tsx`, `test/analyticsPages.test.tsx` |
| `FirmaZakazkyTab` | `CompanyContractsTab` | file + component | same |
| `FirmaSietTab` | `CompanyNetworkTab` | file + component | same |
| `FirmaPartneriTab` | `CompanyPartnersTab` | file + component | same |
| `FirmaCpvTab` | `CompanyCpvTab` | file + component | same |
| `pages/analytics/PrehladPage.tsx` / `PrehladPage` | `OverviewPage.tsx` / `OverviewPage` | file + component | router, `test/analyticsPages.test.tsx` |
| `pages/analytics/KoncentraciaPage.tsx` / `KoncentraciaPage` | `ConcentrationPage.tsx` / `ConcentrationPage` | file + component | same |
| `pages/analytics/PokrytiePage.tsx` / `PokrytiePage` | `CoveragePage.tsx` / `CoveragePage` | file + component | same |
| `'/analytika'`, `'/firmy'`, `'/zakazky'` nav items | `'/analytics'`, `'/companies'`, `'/contracts'` | strings | `components/layout/Header.tsx:7-9` |
| tab `to` strings `/firma/${ico}/{prehlad,zakazky,siet,partneri,cpv}` and `to="/firmy"` | `/company/${ico}/{overview,contracts,network,partners,cpv}`, `/companies` | strings | `pages/CompanyPage.tsx:46,59,67-71,78` |
| `/firma/${…}` | `/company/${…}` | strings | `components/layout/Layout.tsx:12`, `components/entity/EntityLink.tsx:18`, `components/search/EntityAutocomplete.tsx:52`, `components/search/GlobalSearch.tsx:52,65`, `pages/CompaniesPage.tsx:149`, `pages/SearchPage.tsx:116` |
| `/zakazky?selected=` | `/contracts?selected=` | strings | `GlobalSearch.tsx:54`, `SearchPage.tsx:147` |
| `/hladaj?q=` | `/search?q=` | strings | `GlobalSearch.tsx:79`, `SearchPage.tsx:42` |
| `AnalyticsLayout` tab paths `prehlad/koncentracia/pokrytie` and `/analytika` | `overview/concentration/coverage`, `/analytics` | strings | `components/analytics/AnalyticsLayout.tsx` |
| `kind: 'firma' \| 'zakazka'`, locals `firmy`, `zakazky`, key prefix `` `firma-${…}` `` | `kind: 'company' \| 'contract'`, `companies`, `contracts`, `` `company-${…}` `` | TS union + variables | `GlobalSearch.tsx:10,24-31,51,131` |
| locals `firmy`, `zakazky`, `firma` | `companies`, `contracts`, `company` | variables | `SearchPage.tsx`, `CompaniesPage.tsx`, `CompanyPage.tsx`, `pages/company/*.tsx`, `pages/analytics/*.tsx` |

### 4.2 API layer (`src/api`)

| Old | New | Kind | Files |
| --- | --- | --- | --- |
| `api/queries/firma.ts` | `api/queries/companies.ts` | file | `queryClient.ts:3`, pages |
| `firmaKeys` / `all: ['firma']` / `partneri: (…) => […, 'partneri', …]` | `companyKeys` / `all: ['company']` / `partners: (…) => […, 'partners', …]` | query keys | `queries/companies.ts`, `queryClient.ts:36`, `test/queryClient.test.ts` |
| `useFirmaProfile` | `useCompanyProfile` | hook | `CompanyPage.tsx`, `CompanyOverviewTab.tsx` |
| `useFirmaPartneri` | `useCompanyPartners` | hook | `CompanyPartnersTab.tsx` |
| `useFirmaCpvProfile` | `useCompanyCpvProfile` | hook | `CompanyCpvTab.tsx` |
| `useFirmyList` | `useCompaniesList` | hook | `CompaniesPage.tsx` |
| `` `/firma/${ico}` ``, `` `/firma/${ico}/partneri?…` ``, `` `/firma/${ico}/cpv-profile` ``, `` `/firmy?…` `` | `` `/companies/${ico}` ``, `` `/companies/${ico}/partners?…` ``, `` `/companies/${ico}/cpv-profile` ``, `` `/companies?…` `` | request paths (2.1) | `queries/companies.ts` |
| `FirmaStatsBlock`, `FirmaStats`, `FirmaTopContract`, `FirmaTopCpv`, `FirmaProfile`, `FirmaCard`, `FirmaListResponse` | `CompanyStatsBlock`, `CompanyStats`, `CompanyTopContract`, `CompanyTopCpv`, `CompanyProfile`, `CompanyCard`, `CompanyListResponse` | TS interfaces | `queries/companies.ts` + importers |
| `FirmaHit`, `ZakazkaHit`, `UnifiedSearchResult.firmy/.zakazky` | `CompanyHit`, `ContractHit`, `.companies/.contracts` | TS interfaces + **JSON keys** (2.2) | `queries/unifiedSearch.ts`, `GlobalSearch.tsx:4`, `SearchPage.tsx` |
| `zakazkyLink`, `zakazkyPeriodLink`, `firmaLink` | `contractsLink`, `contractsPeriodLink`, `companyLink` | functions | `lib/analyticsLinks.ts`, `pages/analytics/*.tsx`, `test/analyticsLinks.test.ts` |
| `analyticsLink(page: 'prehlad' \| 'koncentracia' \| 'cpv' \| 'pokrytie')` → `` `/analytika/${page}` `` | `'overview' \| 'concentration' \| 'cpv' \| 'coverage'` → `` `/analytics/${page}` `` | union + string | `lib/analyticsLinks.ts:25-32`, callers (`HhiBadge`, `HhiTrendChart`, `SourceCards`, `TimeseriesChart`, `CompanyOverviewTab`) |
| comments "`/analytika/prehlad`" | "`/analytics/overview`" | comments | `api/queries/analytics.ts:25`, `hooks/useAnalyticsFilters.ts:38` |

### 4.3 i18n keys (`src/i18n/sk.ts` — keys only, every value byte-identical)

| Old key | New key | Collision note |
| --- | --- | --- |
| `nav.firmy` | `nav.companies` | |
| `nav.zakazky` | `nav.contracts` | |
| `globalSearch.sectionFirmy` / `.sectionZakazky` | `.sectionCompanies` / `.sectionContracts` | |
| `analytics.tabs.prehlad` / `.koncentracia` / `.pokrytie` | `.overview` / `.concentration` / `.coverage` | `analytics.tabs.cpv` unchanged |
| `analytics.prehlad` (block) | `analytics.overview` | |
| `analytics.koncentracia` (block) | `analytics.concentration` | top-level `concentration` block (line 118) is a different namespace — no clash |
| `analytics.pokrytie` (block) | `analytics.coverage` | |
| `firma` (block) | `company` | |
| `firma.breadcrumbFirmy` | `company.breadcrumbCompanies` | |
| `firma.tabPrehlad` / `.tabZakazky` / `.tabSiet` / `.tabPartneri` | `company.tabOverview` / `.tabContracts` / `.tabNetwork` / `.tabPartners` | `.tabCpv` unchanged |
| `firma.kpiZakazky` / `.kpiHodnota` / `.kpiPosledna` | `company.kpiContracts` / `.kpiValue` / `.kpiLast` | |
| `firma.zakazkyEmpty` / `.zakazkyEmptyHint` | `company.contractsEmpty` / `.contractsEmptyHint` | |
| `firma.sietTitle` / `.sietNoData` / `.sietNoDataHint` | `company.networkTitle` / `.networkNoData` / `.networkNoDataHint` | used by `components/graph/EgoNetwork.tsx` |
| `firma.partneriEmpty` / `.partneriEmptyHint` | `company.partnersEmpty` / `.partnersEmptyHint` | |
| `firma.colRola` / `.colZakazky` / `.colHodnota` / `.colPosledna` | `company.colRole` / `.colContracts` / `.colValue` / `.colLast` | `company` block has no existing `colRole/colContracts/colValue` (those live in `firmy`) |
| `firmy` (block) | `companies` | |
| `hladaj` (block) | `searchPage` | **not** `search`: the existing top-level `search` block (line 51) is a shared namespace used by `EntityAutocomplete`, `GlobalSearch` and `OverviewPage` columns |
| `hladaj.tabFirmy` / `.tabZakazky` | `searchPage.tabCompanies` / `.tabContracts` | |

Keys that look Slovak but stay: `vestnik`, `crz`, `ted`, `itms`, `uvo` (source nouns), `ico`,
`icoLabel`, `icoPlaceholder`, `icoValue`, `hhi*`, `cpv*`, `pinpoint`. `nav.search`, `nav.suppliers`,
`nav.procurers`, `nav.pinpoint` and the `suppliers`/`procurers`/`concentration` blocks are
pre-existing English keys and untouched.

### 4.4 Tests and fixtures (`src/test`)

| Old | New | Kind |
| --- | --- | --- |
| `test/firma.test.tsx` | `test/company.test.tsx` | file |
| `test/zakazkyFilters.test.tsx` | `test/contractsFilters.test.tsx` | file |
| `renderFirma` | `renderCompany` | helper |
| `firmyLink`, `zakazkyLink` locals | `companiesLink`, `contractsLink` | variables in `test/layout.test.tsx` |
| `initialEntries` / `MemoryRouter` paths `/analytika/*`, `/firma/*`, `/firmy`, `/zakazky`, `/hladaj` | per 2.3 | strings in `analyticsPages`, `analyticsFilters`, `analyticsLinks`, `chartCard`, `entityLinks`, `layout`, `urlFilters`, `states`, `autocomplete`, `company` tests |
| `data.firmy` / `data.zakazky` mock responses | `.companies` / `.contracts` | JSON keys in `GlobalSearch`/`SearchPage` tests |
| i18n key references in tests (`sk.firma.*`, `sk.analytics.prehlad.*`, …) | per 4.3 | |
| **add** redirect tests | one `it` per row of the 2.3 redirect table asserting pathname **and** `?x=1` survive | `test/router.test.tsx` (new) |
| Slovak **values** asserted in tests (`'Prehľad'`, `'Partneri'`, `'Stavebná …'`, `'Hodnota'`, `'Zdroj'`) | keep | they assert rendered UI text |

`README.md` (`src/uvo-gui-react/README.md:33-38`) route list → new paths (frontend agent updates
it since it lives in its directory).

## 5. Docs to update afterwards (documenter, after both merges)

- `CLAUDE.md:112` analytics route line (`/analytika/{…}` → `/analytics/{overview,concentration,cpv,coverage}`)
  and the "React GUI notes" bullet on API paths; add one line that `/api/firma*`/`/api/firmy` are
  hidden aliases scheduled for removal.
- `docs/backend.md:138` endpoint list → `/api/companies*`.
- `src/uvo-gui-react/README.md` (done by frontend agent, verify).
- `.claude/agents/*.md` and `.claude/skills/**`: grep showed no references; re-check after merge.
- Leave `docs/superpowers/**`, `docs/plans/2026-10-19-analytics-dashboards-plan.md`,
  `docs/specs/2026-10-19-analytics-dashboards.md`, `docs/architecture/ports-and-adapters-plan.md` as
  historical records.

## 6. Verification

Backend (`uv`):

```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run lint-imports
uv run pytest tests/ --ignore=tests/e2e -q
docker compose up -d --wait && uv run pytest tests/e2e/ -v        # E2E is the only real-system check
curl -sf localhost:8001/openapi.json | jq -r '.paths | keys[]' | grep -E 'firma|firmy' && echo "ALIAS LEAKED INTO SCHEMA" || true
curl -s -o /dev/null -w '%{http_code}\n' localhost:8001/api/firma/00000000          # alias: 404 (not 405/422)
```

Frontend:

```bash
cd src/uvo-gui-react && npm ci && npm run lint && npx tsc -b && npm test -- --run && npm run build
```

Final grep — must return **only** allowed hits. Run from the repo root after both merges:

```bash
grep -rniE --exclude-dir={dist,node_modules,.git,.codegraph,superpowers,.venv,__pycache__} \
  --include='*.py' --include='*.ts' --include='*.tsx' --include='*.yml' --include='*.yaml' \
  --include='*.json' --include='*.conf' --include='*.sh' --include='*.toml' \
  '(firma|firmy|zakaz|hladaj|analytik|prehlad|koncentr|pokryt|siet|partneri|obstarav|dodavat|zadavat|nazov|stav|suma|hodnota|datum|podiel|zdroj|oznamen|vyhlad)' . \
  | grep -vE 'src/uvo-gui-react/src/i18n/sk\.ts' \
  | grep -vE 'src/uvo_core/domain/data/cpv_labels\.json|tests/fixtures/analytics_notices\.json' \
  | grep -vE "(obstaravatelSubjekt|zadavatel|subjekt|dodavatelia|celkovaSumaZmluvy|celkovaHodnotaZmluvy|predpokladanaHodnotaZakazky|datumZverejneniaVoVestniku|verejneObstaravania|zmluvyVerejneObstaravanie|hlavnyDodavatelDodavatelObstaravatel|pocetPrijatychPonuk|\"stav\"|\"nazov\"|'stav'|'nazov')" \
  | grep -vE 'routers/companies\.py:.*(/api/firma|/api/firmy)|test_companies.*\.py:.*(/api/firma|/api/firmy)|uvo-api-performance\.json:.*firma' \
  | grep -vE 'router\.tsx:.*(analytika|firma|firmy|zakazky|hladaj)|router\.test\.tsx' \
  | grep -vE '(Stavb|stavebn|Doprastav|Vyhladavanie|Zastaveny|Zaostava|nastav|scoring\.py)'
```

Allowlist, in the same order as the filters: (1) all `sk.ts` values; (2) Slovak data files;
(3) raw ITMS/Vestník payload keys in extractors, transformers, `scripts/enrich_itms_procurers.py`
and their tests; (4) the alias path strings in `routers/companies.py`, their tests, and the
Grafana regex (all removed with the aliases in section 7); (5) the old-path strings in the SPA
redirect table and its test; (6) Slovak test data / HTML title / the `stavebn` CPV token in
`domain/scoring.py`. Anything else is a miss. Also: `git ls-files | grep -iE 'firma|firmy|zakazky|hladaj|prehlad|koncentracia|pokrytie'` must be empty.

## 7. Rollout notes

- **Deploy API and GUI together.** The `/api/search/unified` key rename is a breaking change for the
  old GUI (it would render empty groups: `data.firmy` is undefined). Aliases make the *new GUI*
  tolerant of an *old API* only for the company endpoints, not for unified search, so the order is:
  merge both branches → CI → `docker-publish.yml` pushes `sha-<7>` for `uvo-api` and `uvo-gui` → bump
  **both** image tags in `stubarag-infra:argocd/manifests/uvo-search/` in one commit. A brief window
  where one pod is old is acceptable (global search shows no results until reload); no data impact.
- Why not serve both key sets: doubling the payload and the TS type for one deploy cycle buys
  nothing here because GUI and API are pinned and rolled in the same ArgoCD commit anyway.
- Aliases stay for **one release**. Removal checklist (a follow-up PR, backend agent): confirm
  `sum(rate(uvo_api_http_requests_total{route=~"/api/(firma|firmy).*"}[7d])) == 0` in Grafana,
  delete `legacy_router` and its tests, drop `firma|firmy` from the dashboard regex, delete the
  CLAUDE.md alias line.
- SPA redirects are **permanent** (bookmarks, external links); they cost nothing and are not
  scheduled for removal.
- Metrics: the `route` label changes from `/api/firma/{ico}` to `/api/companies/{ico}`; any ad-hoc
  Grafana panel or saved query that hard-codes the old template needs the regex in 3.5.
- No Mongo/Neo4j/Redis/Vault/ESO change; no env var change; no migration.
