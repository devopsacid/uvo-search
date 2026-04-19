# GUI Search, List, and Graph Rework — Design

**Date:** 2026-04-19
**Status:** Approved (brainstorming)
**Scope:** `src/uvo_mcp/`, `src/uvo_gui/`, `docker-compose.yml`, `scripts/`

## Problem

The NiceGUI frontend is unresponsive to search:

- `search_completed_procurements`, `find_procurer`, `find_supplier` use MongoDB `$text` search. `$text` requires whole-token matches against a language-stemmed index; partial strings like `fakulta` do not match documents containing `Fakulta`, `Fakultá`, `FAKULTA`, or `fakul*`.
- Diacritics are not folded.
- There is no way to "list everything" paginated.
- Neo4j is running and MCP graph tools exist (`find_supplier_concentration`, `find_related_organisations`, `get_procurement_network`), but no GUI consumes them.

## Goals

1. Case-insensitive, diacritic-insensitive, partial-match search across procurements, procurers, and suppliers.
2. User-friendly query patterns: wildcard `*` and quoted `"exact phrase"`.
3. Live autocomplete with typed entity suggestions.
4. Paginated, sortable list-all views for procurers, suppliers, procurements.
5. New "Sieť vzťahov" (relationship network) tab with interactive graph visualisation backed by Neo4j.

## Non-Goals

- Full boolean query syntax (AND/OR/NOT, field:value).
- Synonyms and custom stopword lists beyond Atlas defaults.
- Precomputed aggregation pipelines for procurer/supplier stats (computed at query time for MVP).
- Replacing Neo4j ingestion; existing pipeline and graph schema remain as-is.

## Architecture

```
docker-compose:
  mongo    mongo:7  →  mongodb/mongodb-atlas-local:latest   (mongot included)
  neo4j    unchanged
  mcp-server      uses $search; adds autocomplete + graph-viz tools
  gui             adds /graph page; reworks search/procurers/suppliers
```

One image swap. Data re-loaded via `mongodump` + `mongorestore`. No new services.

## Atlas Search indexes

Three `searchIndex` definitions created at MCP server startup (idempotent — `createSearchIndex` called only if index of that name is missing).

### Custom analyzer

```json
{
  "name": "sk_folding",
  "tokenizer": { "type": "standard" },
  "tokenFilters": [
    { "type": "lowercase" },
    { "type": "icuFolding" }
  ]
}
```

Applied to every text field below so `fakulta` ≈ `Fakultá` ≈ `FAKULTA`.

### `procurers` / `suppliers`

```json
{
  "analyzer": "sk_folding",
  "searchAnalyzer": "sk_folding",
  "mappings": {
    "dynamic": false,
    "fields": {
      "name": [
        { "type": "string" },
        { "type": "autocomplete", "tokenization": "edgeGram",
          "minGrams": 2, "maxGrams": 15, "foldDiacritics": true }
      ],
      "ico": { "type": "token" }
    }
  }
}
```

### `notices`

```json
{
  "analyzer": "sk_folding",
  "searchAnalyzer": "sk_folding",
  "mappings": {
    "dynamic": false,
    "fields": {
      "title":                  { "type": "string" },
      "description":            { "type": "string" },
      "procurer.name":          { "type": "string" },
      "awards.supplier.name":   { "type": "string" },
      "cpv_code":               { "type": "token" },
      "publication_date":       { "type": "date" }
    }
  }
}
```

### Provisioning

`src/uvo_mcp/search_indexes.py`:

- Module-level `INDEX_DEFINITIONS: dict[str, dict]` mapping collection name → index spec.
- `async def ensure_indexes(db)`: for each collection, list search indexes; if the named index is absent, call `db[coll].create_search_index({"name": "default", "definition": ...})`.
- Invoked once from `AppContext` lifespan after Mongo connection succeeds.
- Logs `"search index ready: <coll>.default"` or skip reason.

## MCP tools

### Query builder — `src/uvo_mcp/search_query.py`

Single public function `build_search_stage(query: str, path: list[str]) -> dict` translating user input into the `$search` stage:

| Input form                    | Output operator                                                    |
|-------------------------------|--------------------------------------------------------------------|
| `""` (empty)                  | `{ "exists": { "path": path[0] } }` — list-all                     |
| `"exact phrase"` (quoted)     | `{ "phrase": { "query": q, "path": path } }`                       |
| contains `*` or `?`           | `{ "wildcard": { "query": q, "path": path, "allowAnalyzedField": true } }` |
| otherwise                     | compound `should`: `autocomplete` (fuzzy=1) + `text` on `path`     |

Always returns a single `$search` stage. Caller wraps in a `$facet` for paginated results + total count.

### Reworked existing tools

All four existing search tools swap their current Mongo query for the aggregation:

```python
pipeline = [
    {"$search": {"index": "default", **build_search_stage(q, paths)}},
    # structured filters (cpv, date range, ico) appended as $match after $search
    {"$facet": {
        "items": [
            {"$sort": sort_spec},
            {"$skip": offset},
            {"$limit": limit},
        ],
        "total": [{"$count": "count"}],
    }},
]
```

`sort_spec` passed through from the caller (default `{"publication_date": -1}` for notices, `{"name": 1}` for entities). Procurers/suppliers tools gain optional `sort_by: "name" | "contract_count" | "total_value"` — count and value computed via a `$lookup` into `notices` inside the aggregation (acceptable perf for MVP).

### New tools

**`search_autocomplete(query, types=["procurer","supplier","notice"], limit=5)`**
Parallel `$search.autocomplete` across requested collections via `asyncio.gather`. Returns:

```json
{ "results": [
  { "type": "procurer", "id": "...", "label": "Fakulta elektrotechniky a informatiky",
    "sublabel": "IČO 12345678" },
  ...
] }
```

Used by the GUI live-search dropdown.

**`graph_ego_network(ico, max_hops=2)`**
Thin wrapper around existing `find_related_organisations` that reshapes to:

```json
{
  "nodes": [ { "id": "ico", "label": "...", "type": "procurer|supplier", "value": 42 } ],
  "edges": [ { "from": "icoA", "to": "icoB", "label": "12 zmlúv", "value": 1234567 } ]
}
```

`value` on edges = total contract value; on nodes = contract count. Ready for `vis-network`.

**`graph_cpv_network(cpv_code, year)`**
Wraps existing `get_procurement_network`, same output shape as above.

## GUI

### New component — `src/uvo_gui/components/search_box.py`

Reusable async input:

- `ui.input(placeholder="🔍 Hľadať… (použite * pre začiatok slova, \"...\" pre presnú frázu)")`
- `on('input', handler)` with 300ms debounce (`ui.timer(0.3, ..., once=True)` pattern, cancelled on new keystroke; module-level `_pending_timer` state).
- Calls `mcp_client.call_tool("search_autocomplete", {...})`, renders a `ui.menu` anchored below the input with results grouped by type.
- Click item → callback argument `on_select(entity)` decides: stay on page (filter) or navigate via `ui.navigate.to(f"/procurer/{ico}")` etc.

Exposes:

```python
def search_box(
    *, placeholder: str = ...,
    types: list[str] = [...],
    on_submit: Callable[[str], Awaitable[None]],
    on_select: Callable[[dict], Awaitable[None]] | None = None,
) -> None
```

### Reworked `pages/search.py`

- Top bar: `search_box(types=["notice","procurer","supplier"])`.
- Left column: `ui.table` with columns *Názov, Obstarávateľ, Hodnota, Dátum*.
  - `pagination={'rowsPerPage': 20}` with `on_pagination_change` → calls MCP tool with new `offset`/`sort`.
  - Empty query = list-all sorted by `publication_date` desc.
  - Row click selects → right panel refresh.
- Right column: detail view (unchanged).

### Reworked `pages/procurers.py` / `pages/suppliers.py`

- Top: `search_box(types=["procurer"])` / `["supplier"]`.
- `ui.table` columns: *Názov, IČO, Počet zákaziek, Celková hodnota €*.
- Server-side sortable/paginated via the new `sort_by` param.
- Row click opens an entity detail dialog (or navigates — TBD during implementation; default: dialog to keep current page state).

### New `pages/graph.py` — "Sieť vzťahov"

Route `/graph`. Two sub-tabs via `ui.tabs`:

1. **Ego-sieť**
   - `search_box(types=["procurer","supplier"])` → on_select sets entity.
   - `ui.slider(min=1, max=3, value=2)` → max hops.
   - Calls `graph_ego_network`; renders in `<div id="graph-canvas">` via `ui.html`.
   - `ui.run_javascript(render_graph_js, payload=nodes_edges_json)`.

2. **CPV-sieť**
   - `ui.input(placeholder="CPV kód, napr. 48000000")`.
   - `ui.number(label="Rok", value=current_year)`.
   - Calls `graph_cpv_network`; renders same way.

Rendering: single shared JS helper loaded via `ui.add_head_html("<script src='https://unpkg.com/vis-network@9/standalone/umd/vis-network.min.js'></script>")`. Helper builds a `vis.Network` with:
- Nodes coloured by type (procurer = `#1d4ed8`, supplier = `#059669`).
- Edges weighted by `value` (contract total).
- Click handler → `ui.navigate.to` for the clicked node's entity page.

### Navigation (`components/layout.py`)

Add `("🕸️", "Sieť", "/graph")` to `NAV_ITEMS`.

## Data migration

### Compose change

```yaml
mongo:
  image: mongodb/mongodb-atlas-local:latest
  environment:
    MONGODB_INITDB_ROOT_USERNAME: uvo
    MONGODB_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD:-changeme}
  volumes:
    - mongo_data:/data/db
  ports:
    - "27017:27017"
  healthcheck:
    test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping')"]
```

### Migration script — `scripts/migrate_to_atlas_local.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${MONGO_PASSWORD:?must be set}"

# 1. dump from legacy mongo:7
docker compose exec -T mongo mongodump \
  --uri="mongodb://uvo:${MONGO_PASSWORD}@localhost:27017/?authSource=admin" \
  --archive > ./mongo-backup.archive

# 2. rename legacy volume, bring up atlas-local
docker compose down
docker volume rm uvo-search_mongo_data_legacy 2>/dev/null || true
docker volume create uvo-search_mongo_data_legacy
# (rename by copy — docker has no rename; tag with timestamp for rollback)
docker run --rm -v uvo-search_mongo_data:/from -v uvo-search_mongo_data_legacy:/to alpine \
  sh -c 'cd /from && tar cf - . | (cd /to && tar xf -)'
docker volume rm uvo-search_mongo_data
docker compose up -d mongo

# 3. restore
docker compose exec -T mongo mongorestore \
  --uri="mongodb://uvo:${MONGO_PASSWORD}@localhost:27017/?authSource=admin" \
  --archive < ./mongo-backup.archive

# 4. bring up everything; MCP server provisions search indexes on startup
docker compose up -d
```

Rollback: `mongo_data_legacy` volume retained until user confirms migration succeeded.

## Testing

### Backend

- `tests/mcp/test_search_query.py` — unit tests for `build_search_stage`: empty, `fakulta`, `"exact phrase"`, `fak*`, `fak?ulta`. Assert exact shape of returned dict.
- `tests/mcp/test_search_tools_integration.py` (marked `integration`) — spins up `mongodb-atlas-local` via testcontainers, seeds 10 fixture docs, verifies `find_procurer("fakulta")` returns docs containing `Fakulta matematiky`, `Prírodovedecká fakulta`, and diacritic variants.
- `tests/mcp/test_autocomplete.py` — verifies typed grouping and `limit` per type.
- `tests/mcp/test_graph_tools.py` — mocks Neo4j driver, asserts output shape matches `{nodes:[...], edges:[...]}`.

### GUI

- `tests/gui/test_search_box.py` — using `user` fixture: type "fakul" → debounce elapses → mock MCP returns 3 items → dropdown visible; click item fires `on_select` with the right entity.
- `tests/gui/test_search_page.py` (update) — empty query lists all; pagination advances; sort changes trigger refetch with new `sort_by`.
- `tests/gui/test_procurers_page.py` / `test_suppliers_page.py` (update) — same as above for entity tables.
- `tests/gui/test_graph_page.py` — page renders, canvas `<div id="graph-canvas">` present; MCP mock returns payload; `ui.run_javascript` called with the JSON.

## Rollout order (maps to implementation plan)

1. Compose swap to `mongodb-atlas-local` + `scripts/migrate_to_atlas_local.sh`. Verify data restored.
2. `search_indexes.py` + provisioning in `AppContext` lifespan.
3. `search_query.py` + rewrite of `search_completed_procurements`, `find_procurer`, `find_supplier` + unit tests.
4. New `search_autocomplete` MCP tool + unit tests.
5. GUI `components/search_box.py` + GUI unit tests.
6. Rework `pages/search.py` to `ui.table` + server-side pagination/sort.
7. Rework `pages/procurers.py` and `pages/suppliers.py` similarly (includes `sort_by` params on MCP tools).
8. `graph_ego_network` + `graph_cpv_network` MCP tools + unit tests.
9. New `pages/graph.py` with vis-network embed + both sub-tabs; nav entry.
10. Docs update (`README.md`: Atlas Search note, graph tab screenshot placeholder, migration instructions).

## Risks

- **Atlas Local image churn** — the image is official but relatively new; pin to a specific tag in compose once implementation confirms a working version.
- **Search index propagation delay** — `createSearchIndex` is async on the server side; tests must poll `listSearchIndexes` until `queryable: true` before asserting results.
- **vis-network via CDN** — if deployment is airgapped, vendor the JS file under `static/`. Out of scope for MVP.
- **`$lookup` cost** for procurer/supplier aggregate stats at query time — if slow (>500ms for typical pages), precompute into a denormalised field on ingest. Deferred until measured.
