# GUI Search, List, and Graph Rework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make GUI search responsive to partial, case- and diacritic-insensitive queries; add paginated list-all entity views; add a Neo4j-backed relationship-graph tab.

**Architecture:** Swap Mongo image to `mongodb/mongodb-atlas-local` (enables `$search`). Rewrite MCP search tools over `$search` with `icuFolding` analyzer + autocomplete. Rework NiceGUI pages to use a reusable live-search component and `ui.table` server-side pagination. New `/graph` page embeds `vis-network` driven by Neo4j data.

**Tech Stack:** Python 3.13, FastMCP, Motor (async Mongo), MongoDB Atlas Local, Neo4j 5, NiceGUI 3.9, vis-network 9 (CDN), pytest, testcontainers.

**Spec:** [docs/superpowers/specs/2026-04-19-gui-search-graph-rework-design.md](../specs/2026-04-19-gui-search-graph-rework-design.md)

---

## File structure

**Create:**
- `scripts/migrate_to_atlas_local.sh` — one-shot data migration
- `src/uvo_mcp/search_indexes.py` — Atlas Search index definitions + provisioning
- `src/uvo_mcp/search_query.py` — `build_search_stage()` query-builder
- `src/uvo_mcp/tools/autocomplete.py` — `search_autocomplete` MCP tool
- `src/uvo_gui/components/search_box.py` — reusable live-search input + dropdown
- `src/uvo_gui/pages/graph.py` — relationship-graph page
- `src/uvo_gui/static/graph_render.js` — vis-network rendering helper
- `tests/mcp/test_search_query.py`
- `tests/mcp/test_search_indexes.py`
- `tests/mcp/test_autocomplete.py`
- `tests/mcp/test_graph_tools.py`
- `tests/gui/test_search_box.py`
- `tests/gui/test_graph_page.py`

**Modify:**
- `docker-compose.yml` — image swap
- `src/uvo_mcp/server.py` — provision indexes at lifespan start
- `src/uvo_mcp/tools/procurements.py` — rewrite over `$search`
- `src/uvo_mcp/tools/subjects.py` — rewrite over `$search` + `sort_by`
- `src/uvo_mcp/tools/graph.py` — reshape outputs to `{nodes,edges}`
- `src/uvo_gui/components/layout.py` — add `🕸️ Sieť` nav entry
- `src/uvo_gui/pages/search.py` — `search_box` + `ui.table` server-side pagination
- `src/uvo_gui/pages/procurers.py` — `search_box` + `ui.table` + sort
- `src/uvo_gui/pages/suppliers.py` — same
- `src/uvo_gui/app.py` — register `/graph` page, static file mount
- `tests/gui/test_search_page.py`, `test_procurers_page.py`, `test_suppliers_page.py` — update
- `README.md` — Atlas note + graph tab + migration

---

## Task 1: Switch Mongo image to Atlas Local

**Files:**
- Modify: `docker-compose.yml:79-95`

- [ ] **Step 1: Update the `mongo` service**

Replace the `mongo` service block with:

```yaml
  mongo:
    image: mongodb/mongodb-atlas-local:latest
    restart: unless-stopped
    environment:
      MONGODB_INITDB_ROOT_USERNAME: uvo
      MONGODB_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD:-changeme}
    volumes:
      - mongo_data:/data/db
    ports:
      - "27017:27017"
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
```

Note: Atlas Local image ignores `MONGO_INITDB_DATABASE`; the DB is created on first write. `mongo-express` env `ME_CONFIG_MONGODB_URL` continues to work unchanged.

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "build: switch mongo service to mongodb-atlas-local for \$search"
```

---

## Task 2: Data migration script

**Files:**
- Create: `scripts/migrate_to_atlas_local.sh`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# Migrate data from legacy mongo:7 volume to mongodb-atlas-local.
# Must be run with the OLD docker-compose.yml still pointing to mongo:7.
# After success, swap the image (Task 1) and start the stack again.
set -euo pipefail
: "${MONGO_PASSWORD:?must be set in environment}"

BACKUP=./mongo-backup.archive

echo "==> Dumping from legacy mongo..."
docker compose exec -T mongo mongodump \
  --uri="mongodb://uvo:${MONGO_PASSWORD}@localhost:27017/?authSource=admin" \
  --archive > "$BACKUP"

echo "==> Stopping stack and preserving legacy volume..."
docker compose down
# Tag legacy volume for rollback; create empty target volume.
docker volume create uvo-search_mongo_data_legacy >/dev/null
docker run --rm \
  -v uvo-search_mongo_data:/from \
  -v uvo-search_mongo_data_legacy:/to \
  alpine sh -c 'cd /from && tar cf - . | (cd /to && tar xf -)'
docker volume rm uvo-search_mongo_data

echo "==> Starting fresh mongo (atlas-local) — make sure compose uses the new image..."
docker compose up -d mongo

echo "==> Waiting for mongo to become healthy..."
for i in $(seq 1 30); do
  if docker compose exec -T mongo mongosh --quiet --eval 'db.adminCommand("ping").ok' | grep -q 1; then
    break
  fi
  sleep 2
done

echo "==> Restoring dump..."
docker compose exec -T mongo mongorestore \
  --uri="mongodb://uvo:${MONGO_PASSWORD}@localhost:27017/?authSource=admin" \
  --archive < "$BACKUP"

echo "==> Done. Legacy volume kept as uvo-search_mongo_data_legacy for rollback."
echo "    Remove with: docker volume rm uvo-search_mongo_data_legacy"
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x scripts/migrate_to_atlas_local.sh
git add scripts/migrate_to_atlas_local.sh
git commit -m "chore: add script to migrate mongo data to atlas-local"
```

Note: Do **not** run the script as part of this plan; it is a one-shot operator action.

---

## Task 3: Search index definitions

**Files:**
- Create: `src/uvo_mcp/search_indexes.py`
- Create: `tests/mcp/test_search_indexes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp/test_search_indexes.py
from uvo_mcp.search_indexes import INDEX_DEFINITIONS


def test_all_three_collections_present():
    assert set(INDEX_DEFINITIONS.keys()) == {"procurers", "suppliers", "notices"}


def test_custom_analyzer_registered_per_index():
    for spec in INDEX_DEFINITIONS.values():
        analyzers = spec["definition"]["analyzers"]
        names = [a["name"] for a in analyzers]
        assert "sk_folding" in names
        filters = next(a for a in analyzers if a["name"] == "sk_folding")["tokenFilters"]
        types = [f["type"] for f in filters]
        assert "lowercase" in types and "icuFolding" in types


def test_procurers_has_autocomplete_on_name():
    fields = INDEX_DEFINITIONS["procurers"]["definition"]["mappings"]["fields"]
    name_types = [f["type"] for f in fields["name"]]
    assert "autocomplete" in name_types
    assert "string" in name_types


def test_notices_fields_include_title_and_cpv_as_token():
    fields = INDEX_DEFINITIONS["notices"]["definition"]["mappings"]["fields"]
    assert fields["title"]["type"] == "string"
    assert fields["cpv_code"]["type"] == "token"
    assert fields["publication_date"]["type"] == "date"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_search_indexes.py -v`
Expected: FAIL — `ModuleNotFoundError: uvo_mcp.search_indexes`

- [ ] **Step 3: Write implementation**

```python
# src/uvo_mcp/search_indexes.py
"""Atlas Search index definitions and idempotent provisioning."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_SK_ANALYZER = {
    "name": "sk_folding",
    "tokenizer": {"type": "standard"},
    "tokenFilters": [{"type": "lowercase"}, {"type": "icuFolding"}],
}

INDEX_DEFINITIONS: dict[str, dict[str, Any]] = {
    "procurers": {
        "name": "default",
        "definition": {
            "analyzers": [_SK_ANALYZER],
            "analyzer": "sk_folding",
            "searchAnalyzer": "sk_folding",
            "mappings": {
                "dynamic": False,
                "fields": {
                    "name": [
                        {"type": "string"},
                        {
                            "type": "autocomplete",
                            "tokenization": "edgeGram",
                            "minGrams": 2,
                            "maxGrams": 15,
                            "foldDiacritics": True,
                        },
                    ],
                    "ico": {"type": "token"},
                },
            },
        },
    },
    "suppliers": {
        "name": "default",
        "definition": {
            "analyzers": [_SK_ANALYZER],
            "analyzer": "sk_folding",
            "searchAnalyzer": "sk_folding",
            "mappings": {
                "dynamic": False,
                "fields": {
                    "name": [
                        {"type": "string"},
                        {
                            "type": "autocomplete",
                            "tokenization": "edgeGram",
                            "minGrams": 2,
                            "maxGrams": 15,
                            "foldDiacritics": True,
                        },
                    ],
                    "ico": {"type": "token"},
                },
            },
        },
    },
    "notices": {
        "name": "default",
        "definition": {
            "analyzers": [_SK_ANALYZER],
            "analyzer": "sk_folding",
            "searchAnalyzer": "sk_folding",
            "mappings": {
                "dynamic": False,
                "fields": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "procurer": {
                        "type": "document",
                        "fields": {"name": {"type": "string"}},
                    },
                    "awards": {
                        "type": "document",
                        "fields": {
                            "supplier": {
                                "type": "document",
                                "fields": {"name": {"type": "string"}},
                            }
                        },
                    },
                    "cpv_code": {"type": "token"},
                    "publication_date": {"type": "date"},
                },
            },
        },
    },
}


async def ensure_indexes(db) -> None:
    """Create each Atlas Search index if missing. Idempotent."""
    for coll, spec in INDEX_DEFINITIONS.items():
        try:
            existing = [i async for i in db[coll].list_search_indexes()]
            names = {i.get("name") for i in existing}
            if spec["name"] in names:
                logger.info("search index already present: %s.%s", coll, spec["name"])
                continue
            await db[coll].create_search_index(spec)
            logger.info("search index created: %s.%s", coll, spec["name"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("search index provisioning failed for %s: %s", coll, exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/mcp/test_search_indexes.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/uvo_mcp/search_indexes.py tests/mcp/test_search_indexes.py
git commit -m "feat(mcp): define atlas search indexes with sk_folding analyzer"
```

---

## Task 4: Wire index provisioning into lifespan

**Files:**
- Modify: `src/uvo_mcp/server.py:31-37`

- [ ] **Step 1: Update the lifespan to call `ensure_indexes`**

Replace the mongo-setup block (lines 31–37) with:

```python
    mongo_db = None
    mongo_client = None
    if settings.mongodb_uri:
        from motor.motor_asyncio import AsyncIOMotorClient

        from uvo_mcp.search_indexes import ensure_indexes

        mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
        mongo_db = mongo_client[settings.mongodb_database]
        logger.info("MongoDB connected: %s", settings.mongodb_database)
        try:
            await ensure_indexes(mongo_db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensure_indexes failed: %s", exc)
```

- [ ] **Step 2: Commit**

```bash
git add src/uvo_mcp/server.py
git commit -m "feat(mcp): provision atlas search indexes at server startup"
```

---

## Task 5: Query builder

**Files:**
- Create: `src/uvo_mcp/search_query.py`
- Create: `tests/mcp/test_search_query.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/mcp/test_search_query.py
from uvo_mcp.search_query import build_search_stage


def test_empty_query_uses_exists():
    stage = build_search_stage("", ["name"])
    assert stage == {"exists": {"path": "name"}}


def test_quoted_phrase_uses_phrase_operator():
    stage = build_search_stage('"Fakulta elektrotechniky"', ["name"])
    assert stage == {
        "phrase": {"query": "Fakulta elektrotechniky", "path": ["name"]}
    }


def test_wildcard_star_uses_wildcard_operator():
    stage = build_search_stage("fakul*", ["name"])
    assert stage == {
        "wildcard": {"query": "fakul*", "path": ["name"], "allowAnalyzedField": True}
    }


def test_question_mark_uses_wildcard_operator():
    stage = build_search_stage("fak?lta", ["name"])
    assert stage["wildcard"]["query"] == "fak?lta"


def test_plain_query_uses_compound_autocomplete_plus_text():
    stage = build_search_stage("fakulta", ["name"])
    should = stage["compound"]["should"]
    assert {"autocomplete": {"query": "fakulta", "path": "name", "fuzzy": {"maxEdits": 1}}} in should
    assert {"text": {"query": "fakulta", "path": ["name"]}} in should


def test_plain_query_multi_path_uses_first_path_for_autocomplete():
    stage = build_search_stage("fakulta", ["title", "description"])
    should = stage["compound"]["should"]
    auto = next(s for s in should if "autocomplete" in s)
    assert auto["autocomplete"]["path"] == "title"
    text = next(s for s in should if "text" in s)
    assert text["text"]["path"] == ["title", "description"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/mcp/test_search_query.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/uvo_mcp/search_query.py
"""Translate user query strings into Atlas $search stage fragments."""

from __future__ import annotations


def build_search_stage(query: str, path: list[str]) -> dict:
    """Return the operator body for a $search stage (without the index key).

    Empty string → list-all via `exists`.
    "quoted phrase" → `phrase` operator.
    Contains * or ? → `wildcard` operator.
    Otherwise → compound of `autocomplete` (fuzzy=1) and `text`.
    """
    q = query.strip()
    if not q:
        return {"exists": {"path": path[0]}}

    if len(q) >= 2 and q.startswith('"') and q.endswith('"'):
        return {"phrase": {"query": q[1:-1], "path": path}}

    if "*" in q or "?" in q:
        return {
            "wildcard": {
                "query": q,
                "path": path,
                "allowAnalyzedField": True,
            }
        }

    return {
        "compound": {
            "should": [
                {
                    "autocomplete": {
                        "query": q,
                        "path": path[0],
                        "fuzzy": {"maxEdits": 1},
                    }
                },
                {"text": {"query": q, "path": path}},
            ]
        }
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/mcp/test_search_query.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/uvo_mcp/search_query.py tests/mcp/test_search_query.py
git commit -m "feat(mcp): add search query builder for atlas \$search"
```

---

## Task 6: Rewrite `find_procurer` / `find_supplier` over `$search`

**Files:**
- Modify: `src/uvo_mcp/tools/subjects.py` (whole file rewrite)
- Modify: `tests/mcp/test_subjects.py` (if it exists) — run existing first to see what shape they assert

- [ ] **Step 1: Inspect existing unit tests**

Run: `uv run pytest tests/mcp/ -k "subject or procurer or supplier" -v`
Note the expected result-dict shape; keep it compatible.

- [ ] **Step 2: Rewrite `src/uvo_mcp/tools/subjects.py`**

```python
"""MCP tools for searching procurers and suppliers via Atlas $search."""

import logging
from typing import Literal

from mcp.server.fastmcp import Context

from uvo_mcp.search_query import build_search_stage
from uvo_mcp.server import AppContext, mcp

logger = logging.getLogger(__name__)

SortBy = Literal["name", "contract_count", "total_value"]


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


def _sort_spec(sort_by: SortBy) -> dict:
    return {
        "name": {"name": 1},
        "contract_count": {"contract_count": -1},
        "total_value": {"total_value": -1},
    }[sort_by]


async def _run_entity_search(
    db,
    collection: str,
    lookup_match_field: str,
    *,
    name_query: str | None,
    ico: str | None,
    sort_by: SortBy,
    limit: int,
    offset: int,
) -> dict:
    if ico:
        # exact ICO match bypasses $search
        filter_ = {"ico": ico}
        total = await db[collection].count_documents(filter_)
        docs = await db[collection].find(filter_).skip(offset).limit(limit).to_list(limit)
        for d in docs:
            d["_id"] = str(d["_id"])
        return {"items": docs, "total": total, "limit": limit, "offset": offset}

    search_stage = {"$search": {"index": "default", **build_search_stage(name_query or "", ["name"])}}

    pipeline: list[dict] = [search_stage]

    # Join notices to compute contract_count / total_value
    pipeline += [
        {
            "$lookup": {
                "from": "notices",
                "localField": "ico",
                "foreignField": lookup_match_field,
                "as": "_notices",
            }
        },
        {
            "$addFields": {
                "contract_count": {"$size": "$_notices"},
                "total_value": {
                    "$sum": {
                        "$map": {
                            "input": "$_notices",
                            "as": "n",
                            "in": {"$ifNull": ["$$n.final_value", 0]},
                        }
                    }
                },
            }
        },
        {"$project": {"_notices": 0}},
    ]

    pipeline += [
        {
            "$facet": {
                "items": [
                    {"$sort": _sort_spec(sort_by)},
                    {"$skip": offset},
                    {"$limit": limit},
                ],
                "total": [{"$count": "count"}],
            }
        }
    ]

    cursor = db[collection].aggregate(pipeline)
    [result] = await cursor.to_list(1)
    items = result.get("items", [])
    for d in items:
        d["_id"] = str(d["_id"])
    total = (result.get("total") or [{"count": 0}])[0].get("count", 0)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@mcp.tool()
async def find_procurer(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    sort_by: SortBy = "name",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search procurers by name substring, wildcard, or phrase."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await _run_entity_search(
        app_ctx.mongo_db,
        "procurers",
        "procurer.ico",
        name_query=name_query,
        ico=ico,
        sort_by=sort_by,
        limit=min(limit, app_ctx.settings.max_page_size),
        offset=max(offset, 0),
    )


@mcp.tool()
async def find_supplier(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    sort_by: SortBy = "name",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search suppliers by name substring, wildcard, or phrase."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await _run_entity_search(
        app_ctx.mongo_db,
        "suppliers",
        "awards.supplier.ico",
        name_query=name_query,
        ico=ico,
        sort_by=sort_by,
        limit=min(limit, app_ctx.settings.max_page_size),
        offset=max(offset, 0),
    )
```

- [ ] **Step 3: Add unit test for pipeline shape**

Create/append to `tests/mcp/test_subjects.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_mcp.tools.subjects import _run_entity_search


@pytest.mark.asyncio
async def test_ico_bypass_uses_find_not_aggregate():
    coll = MagicMock()
    coll.count_documents = AsyncMock(return_value=1)
    cursor = MagicMock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[{"_id": "x", "ico": "123", "name": "Acme"}])
    coll.find = MagicMock(return_value=cursor)
    db = {"procurers": coll}

    out = await _run_entity_search(
        db, "procurers", "procurer.ico",
        name_query=None, ico="123", sort_by="name", limit=10, offset=0,
    )
    assert out["total"] == 1
    assert out["items"][0]["ico"] == "123"
    coll.find.assert_called_once_with({"ico": "123"})


@pytest.mark.asyncio
async def test_name_query_builds_search_pipeline():
    agg = MagicMock()
    agg.to_list = AsyncMock(return_value=[{"items": [{"_id": "a", "name": "Fakulta"}], "total": [{"count": 1}]}])
    coll = MagicMock()
    coll.aggregate = MagicMock(return_value=agg)
    db = {"procurers": coll}

    out = await _run_entity_search(
        db, "procurers", "procurer.ico",
        name_query="fakul", ico=None, sort_by="contract_count", limit=5, offset=0,
    )
    assert out["total"] == 1
    # Pipeline must start with $search, contain $lookup and $facet
    (pipeline,) = coll.aggregate.call_args.args
    assert "$search" in pipeline[0]
    assert any("$lookup" in s for s in pipeline)
    assert "$facet" in pipeline[-1]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_subjects.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/uvo_mcp/tools/subjects.py tests/mcp/test_subjects.py
git commit -m "feat(mcp): rewrite find_procurer/find_supplier on atlas \$search"
```

---

## Task 7: Rewrite `search_completed_procurements` over `$search`

**Files:**
- Modify: `src/uvo_mcp/tools/procurements.py`
- Modify: `tests/mcp/test_procurements.py` (if exists; otherwise create)

- [ ] **Step 1: Rewrite `_search_mongo_procurements`**

Replace the body of [src/uvo_mcp/tools/procurements.py](src/uvo_mcp/tools/procurements.py) `_search_mongo_procurements` (lines 16–52) with:

```python
async def _search_mongo_procurements(
    db,
    *,
    text_query: str | None = None,
    cpv_codes: list[str] | None = None,
    procurer_id: str | None = None,
    supplier_ico: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Query MongoDB notices via Atlas $search."""
    from uvo_mcp.search_query import build_search_stage

    match_extra: dict = {"notice_type": "contract_award"}
    if cpv_codes:
        match_extra["cpv_code"] = {"$in": cpv_codes}
    if procurer_id:
        match_extra["procurer.ico"] = procurer_id
    if supplier_ico:
        match_extra["awards.supplier.ico"] = supplier_ico
    if date_from:
        match_extra.setdefault("publication_date", {})["$gte"] = date_from
    if date_to:
        match_extra.setdefault("publication_date", {})["$lte"] = date_to

    search_stage = {
        "$search": {
            "index": "default",
            **build_search_stage(
                text_query or "",
                ["title", "description", "procurer.name", "awards.supplier.name"],
            ),
        }
    }

    pipeline = [
        search_stage,
        {"$match": match_extra},
        {
            "$facet": {
                "items": [
                    {"$sort": {"publication_date": -1}},
                    {"$skip": offset},
                    {"$limit": limit},
                ],
                "total": [{"$count": "count"}],
            }
        },
    ]

    cursor = db.notices.aggregate(pipeline)
    [result] = await cursor.to_list(1)
    items = result.get("items", [])
    for d in items:
        d["_id"] = str(d["_id"])
    total = (result.get("total") or [{"count": 0}])[0].get("count", 0)
    return {"items": items, "total": total, "limit": limit, "offset": offset}
```

Update the tool return key from `data` to `items` for consistency with the GUI (`SearchState._fetch` already reads `items` and `total`). Existing tool signature stays unchanged.

- [ ] **Step 2: Update/add tests**

Append to `tests/mcp/test_procurements.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_mcp.tools.procurements import _search_mongo_procurements


@pytest.mark.asyncio
async def test_pipeline_has_search_match_and_facet():
    agg = MagicMock()
    agg.to_list = AsyncMock(return_value=[{"items": [{"_id": "n1", "title": "X"}], "total": [{"count": 1}]}])
    db = MagicMock()
    db.notices.aggregate = MagicMock(return_value=agg)

    out = await _search_mongo_procurements(db, text_query="fakulta", date_from="2024-01-01")
    assert out["total"] == 1
    (pipeline,) = db.notices.aggregate.call_args.args
    assert "$search" in pipeline[0]
    assert pipeline[1]["$match"]["notice_type"] == "contract_award"
    assert pipeline[1]["$match"]["publication_date"] == {"$gte": "2024-01-01"}
    assert "$facet" in pipeline[2]
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/mcp/test_procurements.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/uvo_mcp/tools/procurements.py tests/mcp/test_procurements.py
git commit -m "feat(mcp): rewrite search_completed_procurements on atlas \$search"
```

---

## Task 8: `search_autocomplete` MCP tool

**Files:**
- Create: `src/uvo_mcp/tools/autocomplete.py`
- Create: `tests/mcp/test_autocomplete.py`
- Modify: `src/uvo_mcp/server.py` (import new tool module)

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp/test_autocomplete.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_mcp.tools.autocomplete import _run_autocomplete


@pytest.mark.asyncio
async def test_autocomplete_parallel_across_collections():
    def make_coll(rows):
        coll = MagicMock()
        agg = MagicMock()
        agg.to_list = AsyncMock(return_value=rows)
        coll.aggregate = MagicMock(return_value=agg)
        return coll

    db = {
        "procurers": make_coll([{"_id": "p1", "ico": "111", "name": "Fakulta A"}]),
        "suppliers": make_coll([{"_id": "s1", "ico": "222", "name": "Firma B"}]),
        "notices":   make_coll([{"_id": "n1", "source_id": "N1", "title": "Dodávka"}]),
    }

    out = await _run_autocomplete(db, "fak", types=["procurer", "supplier", "notice"], limit=5)
    types = {r["type"] for r in out["results"]}
    assert types == {"procurer", "supplier", "notice"}
    procurer = next(r for r in out["results"] if r["type"] == "procurer")
    assert procurer["label"] == "Fakulta A"
    assert procurer["sublabel"] == "IČO 111"


@pytest.mark.asyncio
async def test_autocomplete_empty_query_returns_empty():
    out = await _run_autocomplete({}, "", types=["procurer"], limit=5)
    assert out == {"results": []}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/mcp/test_autocomplete.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

```python
# src/uvo_mcp/tools/autocomplete.py
"""Autocomplete across procurers, suppliers, and notices."""

import asyncio
import logging
from typing import Iterable

from mcp.server.fastmcp import Context

from uvo_mcp.server import AppContext, mcp

logger = logging.getLogger(__name__)

_COLLECTION = {"procurer": "procurers", "supplier": "suppliers", "notice": "notices"}
_PATH = {"procurer": "name", "supplier": "name", "notice": "title"}
_ID = {"procurer": "ico", "supplier": "ico", "notice": "source_id"}
_LABEL = {"procurer": "name", "supplier": "name", "notice": "title"}


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


async def _one_collection(db, entity_type: str, query: str, limit: int) -> list[dict]:
    coll = db[_COLLECTION[entity_type]]
    pipeline = [
        {
            "$search": {
                "index": "default",
                "autocomplete": {"query": query, "path": _PATH[entity_type], "fuzzy": {"maxEdits": 1}},
            }
        },
        {"$limit": limit},
        {"$project": {"_id": 1, _ID[entity_type]: 1, _LABEL[entity_type]: 1, "ico": 1}},
    ]
    rows = await coll.aggregate(pipeline).to_list(limit)
    out = []
    for r in rows:
        out.append(
            {
                "type": entity_type,
                "id": r.get(_ID[entity_type]) or str(r["_id"]),
                "label": r.get(_LABEL[entity_type], "-"),
                "sublabel": f"IČO {r['ico']}" if r.get("ico") else "",
            }
        )
    return out


async def _run_autocomplete(
    db, query: str, *, types: Iterable[str], limit: int
) -> dict:
    q = query.strip()
    if not q:
        return {"results": []}

    tasks = [_one_collection(db, t, q, limit) for t in types if t in _COLLECTION]
    results_per_type = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[dict] = []
    for bucket in results_per_type:
        if isinstance(bucket, Exception):
            logger.warning("autocomplete bucket failed: %s", bucket)
            continue
        out.extend(bucket)
    return {"results": out}


@mcp.tool()
async def search_autocomplete(
    ctx: Context,
    query: str,
    types: list[str] | None = None,
    limit: int = 5,
) -> dict:
    """Return up to `limit` suggestions per requested entity type for live search."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await _run_autocomplete(
        app_ctx.mongo_db,
        query,
        types=types or ["procurer", "supplier", "notice"],
        limit=min(max(limit, 1), 20),
    )
```

- [ ] **Step 4: Register tool module in server**

In [src/uvo_mcp/server.py:75-77](src/uvo_mcp/server.py#L75-L77), add the import below the existing three:

```python
import uvo_mcp.tools.procurements  # noqa: F401, E402
import uvo_mcp.tools.subjects  # noqa: F401, E402
import uvo_mcp.tools.graph  # noqa: F401, E402
import uvo_mcp.tools.autocomplete  # noqa: F401, E402
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/mcp/test_autocomplete.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add src/uvo_mcp/tools/autocomplete.py tests/mcp/test_autocomplete.py src/uvo_mcp/server.py
git commit -m "feat(mcp): add search_autocomplete tool across entity collections"
```

---

## Task 9: Reshape graph tools to `{nodes, edges}`

**Files:**
- Modify: `src/uvo_mcp/tools/graph.py`
- Create: `tests/mcp/test_graph_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp/test_graph_tools.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_mcp.tools.graph import _build_ego_graph, _build_cpv_graph


def test_build_ego_graph_shape():
    start = {"ico": "111", "name": "Fakulta A", "type": "procurer", "contract_count": 5}
    related_rows = [
        {"name": "Firma B", "ico": "222", "type": "Supplier", "hops": 1, "contract_count": 3, "total_value": 50000},
        {"name": "Inštitúcia C", "ico": "333", "type": "Procurer", "hops": 2, "contract_count": 1, "total_value": 12000},
    ]
    graph = _build_ego_graph(start, related_rows)

    ids = {n["id"] for n in graph["nodes"]}
    assert ids == {"111", "222", "333"}
    start_node = next(n for n in graph["nodes"] if n["id"] == "111")
    assert start_node["type"] == "procurer"
    assert start_node["value"] == 5
    assert {e["from"] for e in graph["edges"]} == {"111"}


def test_build_cpv_graph_shape():
    rows = [
        {"procurer_ico": "111", "procurer_name": "F A", "supplier_ico": "222", "supplier_name": "S B",
         "contract_count": 2, "total_value": 10000},
    ]
    graph = _build_cpv_graph(rows)
    assert {n["id"] for n in graph["nodes"]} == {"111", "222"}
    edge = graph["edges"][0]
    assert edge["from"] == "111"
    assert edge["to"] == "222"
    assert edge["value"] == 10000
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/mcp/test_graph_tools.py -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Add the two shape-builder helpers to `src/uvo_mcp/tools/graph.py`**

Append to [src/uvo_mcp/tools/graph.py](src/uvo_mcp/tools/graph.py):

```python
def _build_ego_graph(start: dict, related: list[dict]) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    nodes[start["ico"]] = {
        "id": start["ico"],
        "label": start.get("name", "-"),
        "type": start.get("type", "procurer"),
        "value": start.get("contract_count", 0),
    }
    for r in related:
        rid = r.get("ico")
        if not rid:
            continue
        nodes[rid] = {
            "id": rid,
            "label": r.get("name", "-"),
            "type": (r.get("type") or "").lower() or "supplier",
            "value": r.get("contract_count", 0),
        }
        edges.append(
            {
                "from": start["ico"],
                "to": rid,
                "label": f"{r.get('contract_count', 0)} zmlúv",
                "value": r.get("total_value", 0),
            }
        )
    return {"nodes": list(nodes.values()), "edges": edges}


def _build_cpv_graph(rows: list[dict]) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for r in rows:
        p_ico, s_ico = r.get("procurer_ico"), r.get("supplier_ico")
        if not p_ico or not s_ico:
            continue
        nodes[p_ico] = {"id": p_ico, "label": r.get("procurer_name", "-"), "type": "procurer", "value": 0}
        nodes[s_ico] = {"id": s_ico, "label": r.get("supplier_name", "-"), "type": "supplier", "value": 0}
        edges.append(
            {
                "from": p_ico,
                "to": s_ico,
                "label": f"{r.get('contract_count', 0)} zmlúv",
                "value": r.get("total_value", 0),
            }
        )
    return {"nodes": list(nodes.values()), "edges": edges}
```

- [ ] **Step 4: Add new tools `graph_ego_network` and `graph_cpv_network`**

Append:

```python
@mcp.tool()
async def graph_ego_network(ctx: Context, ico: str, max_hops: int = 2) -> dict:
    """Return {nodes, edges} ego-network around the given ICO for frontend rendering."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.neo4j_driver is None:
        return {"error": "Neo4j not connected", "status_code": 503}
    if max_hops > 3:
        max_hops = 3

    async with app_ctx.neo4j_driver.session() as session:
        start_rec = await (await session.run(
            """
            MATCH (s) WHERE (s:Procurer OR s:Supplier) AND s.ico = $ico
            OPTIONAL MATCH (s)-[r]-()
            RETURN s.name AS name, s.ico AS ico,
                   labels(s)[0] AS type, count(r) AS contract_count
            """,
            ico=ico,
        )).single()
        if not start_rec:
            return {"nodes": [], "edges": []}
        start = dict(start_rec)
        start["type"] = (start.get("type") or "").lower()

        result = await session.run(
            f"""
            MATCH (a {{ico: $ico}})
            MATCH path = (a)-[*1..{max_hops}]-(b)
            WHERE (b:Procurer OR b:Supplier) AND b.ico <> $ico
            WITH b, length(path) AS hops,
                 [x IN relationships(path) | x] AS rels
            RETURN DISTINCT b.name AS name, b.ico AS ico,
                   labels(b)[0] AS type, min(hops) AS hops,
                   count(*) AS contract_count,
                   sum([r IN rels WHERE type(r)='AWARDED_TO' | r.value][0]) AS total_value
            ORDER BY hops, name
            LIMIT 50
            """,
            ico=ico,
        )
        related = [dict(rec) async for rec in result]

    return _build_ego_graph(start, related)


@mcp.tool()
async def graph_cpv_network(ctx: Context, cpv_code: str, year: int) -> dict:
    """Return {nodes, edges} bipartite network for CPV prefix + year."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.neo4j_driver is None:
        return {"error": "Neo4j not connected", "status_code": 503}

    async with app_ctx.neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Procurer)-[:ISSUED]->(n:Notice)-[:AWARDED_TO]->(s:Supplier)
            WHERE n.cpv_code STARTS WITH $cpv_prefix
              AND n.publication_date.year = $year
            RETURN p.ico AS procurer_ico, p.name AS procurer_name,
                   s.ico AS supplier_ico, s.name AS supplier_name,
                   count(n) AS contract_count,
                   sum(n.final_value) AS total_value
            ORDER BY total_value DESC
            LIMIT 100
            """,
            cpv_prefix=cpv_code[:8],
            year=year,
        )
        rows = [dict(r) async for r in result]

    return _build_cpv_graph(rows)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/mcp/test_graph_tools.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/uvo_mcp/tools/graph.py tests/mcp/test_graph_tools.py
git commit -m "feat(mcp): add graph_ego_network and graph_cpv_network tools"
```

---

## Task 10: `search_box` reusable component

**Files:**
- Create: `src/uvo_gui/components/search_box.py`
- Create: `tests/gui/test_search_box.py`

- [ ] **Step 1: Write failing test**

```python
# tests/gui/test_search_box.py
from unittest.mock import AsyncMock

import pytest
from nicegui import ui
from nicegui.testing import User


@pytest.mark.asyncio
async def test_search_box_triggers_autocomplete_and_dropdown(user: User, monkeypatch):
    mock = AsyncMock(return_value={"results": [
        {"type": "procurer", "id": "111", "label": "Fakulta A", "sublabel": "IČO 111"},
    ]})
    monkeypatch.setattr("uvo_gui.components.search_box.mcp_client.call_tool", mock)

    captured = {}

    from uvo_gui.components.search_box import search_box

    @ui.page("/sb")
    def page():
        async def on_submit(q): captured["submit"] = q
        async def on_select(item): captured["select"] = item
        search_box(on_submit=on_submit, on_select=on_select)

    await user.open("/sb")
    user.find("input").type("fak")
    # Debounce=0 for tests: search_box should expose a test hook; we flush by invoking its handler:
    from uvo_gui.components.search_box import _flush_for_tests
    await _flush_for_tests()

    await user.should_see("Fakulta A")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/gui/test_search_box.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement component**

```python
# src/uvo_gui/components/search_box.py
"""Reusable live-search input with autocomplete dropdown."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from nicegui import ui

from uvo_gui import mcp_client

logger = logging.getLogger(__name__)

_DEBOUNCE_SEC = 0.3
_pending_tasks: list[asyncio.Task] = []  # test hook


async def _flush_for_tests() -> None:
    while _pending_tasks:
        t = _pending_tasks.pop(0)
        try:
            await t
        except Exception:  # noqa: BLE001
            pass


def search_box(
    *,
    placeholder: str = '🔍 Hľadať… (použite * pre začiatok slova, "..." pre presnú frázu)',
    types: list[str] | None = None,
    on_submit: Callable[[str], Awaitable[None]] | None = None,
    on_select: Callable[[dict], Awaitable[None]] | None = None,
    debounce: float = _DEBOUNCE_SEC,
) -> None:
    """Render an input with a menu that lists live autocomplete results."""
    types = types or ["procurer", "supplier", "notice"]
    state = {"query": "", "task": None, "results": []}

    @ui.refreshable
    def dropdown() -> None:
        if not state["results"]:
            return
        with ui.card().classes("absolute z-50 w-full mt-1 p-0 shadow-lg bg-white"):
            for item in state["results"]:
                row = ui.row().classes("w-full p-2 hover:bg-slate-50 cursor-pointer items-center gap-2")
                with row:
                    icon = {"procurer": "🏢", "supplier": "🤝", "notice": "📄"}.get(item["type"], "•")
                    ui.label(icon).classes("text-sm")
                    with ui.column().classes("gap-0"):
                        ui.label(item["label"]).classes("text-sm font-semibold text-slate-800")
                        if item.get("sublabel"):
                            ui.label(item["sublabel"]).classes("text-xs text-slate-400")
                row.on("click", lambda i=item: asyncio.ensure_future(_handle_select(i)))

    async def _handle_select(item: dict) -> None:
        state["results"] = []
        dropdown.refresh()
        if on_select:
            await on_select(item)

    async def _fetch(q: str) -> None:
        try:
            data = await mcp_client.call_tool(
                "search_autocomplete", {"query": q, "types": types, "limit": 5}
            )
            state["results"] = data.get("results", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("autocomplete failed: %s", exc)
            state["results"] = []
        dropdown.refresh()

    async def _debounced_fetch(q: str) -> None:
        await asyncio.sleep(debounce)
        if q == state["query"]:
            await _fetch(q)

    def _on_input(e) -> None:
        state["query"] = e.value or ""
        if state["task"] and not state["task"].done():
            state["task"].cancel()
        if not state["query"].strip():
            state["results"] = []
            dropdown.refresh()
            return
        task = asyncio.ensure_future(_debounced_fetch(state["query"]))
        state["task"] = task
        _pending_tasks.append(task)

    async def _on_submit() -> None:
        if on_submit:
            await on_submit(state["query"])

    with ui.column().classes("w-full relative"):
        ui.input(placeholder=placeholder).classes("w-full").on(
            "input", lambda e: _on_input(e)
        ).on("keydown.enter", lambda _: asyncio.ensure_future(_on_submit()))
        dropdown()
```

Note: for the test, set `debounce=0` via a keyword if needed. Update the test to pass `debounce=0` to `search_box` when calling it inside `page()`.

Update the test's `page()` to:

```python
    @ui.page("/sb")
    def page():
        async def on_submit(q): captured["submit"] = q
        async def on_select(item): captured["select"] = item
        search_box(on_submit=on_submit, on_select=on_select, debounce=0)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/gui/test_search_box.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/uvo_gui/components/search_box.py tests/gui/test_search_box.py
git commit -m "feat(gui): reusable search_box with autocomplete dropdown"
```

---

## Task 11: Rework `pages/search.py` with `ui.table`

**Files:**
- Modify: `src/uvo_gui/pages/search.py`
- Modify: `tests/gui/test_search_page.py`

- [ ] **Step 1: Rewrite `src/uvo_gui/pages/search.py`**

Replace the whole file with:

```python
"""Search page — sortable/paginated notices table + detail panel."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui

from uvo_gui import mcp_client
from uvo_gui.components.layout import layout
from uvo_gui.components.search_box import search_box

logger = logging.getLogger(__name__)


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
        pag = e.args if isinstance(e.args, dict) else e.args[0]
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
        except Exception as exc:  # noqa: BLE001
            logger.error("search failed: %s", exc)
            self.error = f"Chyba pri vyhľadávaní: {exc}"
            self.rows = []; self.total = 0
        finally:
            self.loading = False
            view.refresh()

    def select(self, row: dict) -> None:
        self.selected = row
        view.refresh()


_state = SearchState()


@ui.refreshable
def view() -> None:
    with ui.row().classes("w-full h-full gap-4"):
        with ui.column().classes("flex-1 h-full gap-2"):
            search_box(
                types=["notice", "procurer", "supplier"],
                on_submit=_state.submit,
                on_select=lambda item: _state.submit(item.get("label", "")),
            )
            if _state.error:
                ui.label(_state.error).classes("text-red-600 text-sm")

            columns = [
                {"name": "title", "label": "Názov", "field": "title", "sortable": True, "align": "left"},
                {"name": "procurer", "label": "Obstarávateľ",
                 "field": lambda r: (r.get("procurer") or {}).get("name", "-"),
                 "sortable": False, "align": "left"},
                {"name": "final_value", "label": "Hodnota €", "field": "final_value",
                 "sortable": True, "align": "right"},
                {"name": "publication_date", "label": "Dátum",
                 "field": "publication_date", "sortable": True, "align": "left"},
            ]
            table = ui.table(
                columns=columns,
                rows=_state.rows,
                row_key="_id",
                pagination={
                    "rowsPerPage": _state.per_page,
                    "page": _state.page,
                    "rowsNumber": _state.total,
                    "sortBy": _state.sort_field,
                    "descending": _state.sort_desc,
                },
            ).props("flat bordered").classes("w-full")
            table.on("request", lambda e: asyncio.ensure_future(_state.on_pagination(e)))
            table.on("rowClick", lambda e: _state.select(e.args[1] if len(e.args) > 1 else {}))

            if _state.loading:
                ui.spinner(size="md").classes("self-center")

        with ui.column().classes("w-96 h-full"):
            with ui.card().classes("w-full h-full p-4"):
                if _state.selected is None:
                    ui.label("Vyberte zákazku zo zoznamu").classes("text-sm text-slate-400")
                else:
                    item = _state.selected
                    ui.label(item.get("title", "-")).classes("text-lg font-semibold text-slate-800 mb-2")
                    ui.label((item.get("procurer") or {}).get("name", "-")).classes(
                        "text-sm text-slate-500 mb-1"
                    )
                    ui.label(f"{item.get('final_value', '-')} €").classes(
                        "text-base text-green-700 font-bold"
                    )
                    ui.label(str(item.get("publication_date", "-"))).classes(
                        "text-sm text-slate-500"
                    )


@ui.page("/")
async def search_page() -> None:
    with layout(current_path="/"):
        view()
        await _state.fetch()
```

- [ ] **Step 2: Update `tests/gui/test_search_page.py`**

Review existing tests; retarget assertions from the old card layout to the new table — minimum two tests to keep:

```python
from unittest.mock import AsyncMock

import pytest
from nicegui.testing import User


@pytest.mark.asyncio
async def test_empty_search_lists_all(user: User, monkeypatch):
    mock = AsyncMock(return_value={
        "items": [{"_id": "n1", "title": "Dodávka A", "final_value": 1000,
                    "publication_date": "2024-01-01",
                    "procurer": {"name": "Mesto X"}}],
        "total": 1,
    })
    monkeypatch.setattr("uvo_gui.pages.search.mcp_client.call_tool", mock)
    await user.open("/")
    await user.should_see("Dodávka A")
    await user.should_see("Mesto X")


@pytest.mark.asyncio
async def test_search_error_shows_message(user: User, monkeypatch):
    mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr("uvo_gui.pages.search.mcp_client.call_tool", mock)
    await user.open("/")
    await user.should_see("Chyba pri vyhľadávaní")
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/gui/test_search_page.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/uvo_gui/pages/search.py tests/gui/test_search_page.py
git commit -m "feat(gui): rework search page with ui.table and search_box"
```

---

## Task 12: Rework `pages/procurers.py`

**Files:**
- Modify: `src/uvo_gui/pages/procurers.py`
- Modify: `tests/gui/test_procurers_page.py`

- [ ] **Step 1: Rewrite the page**

```python
"""Procurers page — search + paginated table of contracting authorities."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui

from uvo_gui import mcp_client
from uvo_gui.components.layout import layout
from uvo_gui.components.search_box import search_box

logger = logging.getLogger(__name__)


@dataclass
class ProcurersState:
    query: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    sort_field: str = "name"
    sort_desc: bool = False
    loading: bool = False
    error: str = ""

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    async def submit(self, q: str) -> None:
        self.query = q
        self.page = 1
        await self.fetch()

    async def on_pagination(self, e) -> None:
        pag = e.args if isinstance(e.args, dict) else e.args[0]
        self.page = pag.get("page", 1)
        self.per_page = pag.get("rowsPerPage", 20)
        self.sort_field = pag.get("sortBy") or self.sort_field
        self.sort_desc = bool(pag.get("descending", False))
        await self.fetch()

    async def fetch(self) -> None:
        self.loading = True
        self.error = ""
        view.refresh()
        try:
            args: dict[str, Any] = {
                "limit": self.per_page, "offset": self.offset,
                "sort_by": self.sort_field if self.sort_field in ("name", "contract_count", "total_value") else "name",
            }
            if self.query:
                args["name_query"] = self.query
            data = await mcp_client.call_tool("find_procurer", args)
            self.rows = data.get("items", [])
            self.total = data.get("total", 0)
        except Exception as exc:  # noqa: BLE001
            logger.error("procurers fetch failed: %s", exc)
            self.error = f"Chyba pri vyhľadávaní: {exc}"
            self.rows = []; self.total = 0
        finally:
            self.loading = False
            view.refresh()


_state = ProcurersState()


@ui.refreshable
def view() -> None:
    with ui.column().classes("w-full gap-4"):
        ui.label("Obstaravatelia").classes("text-xl font-semibold text-slate-800")
        search_box(types=["procurer"], on_submit=_state.submit,
                   on_select=lambda i: _state.submit(i.get("label", "")))
        if _state.error:
            ui.label(_state.error).classes("text-red-600 text-sm")

        columns = [
            {"name": "name", "label": "Názov", "field": "name", "sortable": True, "align": "left"},
            {"name": "ico", "label": "IČO", "field": "ico", "sortable": False, "align": "left"},
            {"name": "contract_count", "label": "Počet zákaziek",
             "field": "contract_count", "sortable": True, "align": "right"},
            {"name": "total_value", "label": "Celková hodnota €",
             "field": "total_value", "sortable": True, "align": "right"},
        ]
        table = ui.table(
            columns=columns,
            rows=_state.rows,
            row_key="ico",
            pagination={
                "rowsPerPage": _state.per_page,
                "page": _state.page,
                "rowsNumber": _state.total,
                "sortBy": _state.sort_field,
                "descending": _state.sort_desc,
            },
        ).props("flat bordered").classes("w-full")
        table.on("request", lambda e: asyncio.ensure_future(_state.on_pagination(e)))

        if _state.loading:
            ui.spinner(size="md").classes("self-center")


@ui.page("/procurers")
async def procurers_page() -> None:
    with layout(current_path="/procurers"):
        view()
        await _state.fetch()
```

- [ ] **Step 2: Update tests**

Replace `tests/gui/test_procurers_page.py` with:

```python
from unittest.mock import AsyncMock

import pytest
from nicegui.testing import User


@pytest.mark.asyncio
async def test_lists_procurers_on_open(user: User, monkeypatch):
    mock = AsyncMock(return_value={
        "items": [{"_id": "p1", "name": "Fakulta Test", "ico": "111",
                    "contract_count": 3, "total_value": 50000}],
        "total": 1,
    })
    monkeypatch.setattr("uvo_gui.pages.procurers.mcp_client.call_tool", mock)
    await user.open("/procurers")
    await user.should_see("Fakulta Test")
    await user.should_see("111")
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/gui/test_procurers_page.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/uvo_gui/pages/procurers.py tests/gui/test_procurers_page.py
git commit -m "feat(gui): rework procurers page with search_box and ui.table"
```

---

## Task 13: Rework `pages/suppliers.py`

**Files:**
- Modify: `src/uvo_gui/pages/suppliers.py`
- Modify: `tests/gui/test_suppliers_page.py`

- [ ] **Step 1: Rewrite the page**

Use the same structure as Task 12 but substituting `suppliers` / `find_supplier` / `types=["supplier"]` / title `Dodavatelia`. Paste:

```python
"""Suppliers page — search + paginated table of awarded suppliers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui

from uvo_gui import mcp_client
from uvo_gui.components.layout import layout
from uvo_gui.components.search_box import search_box

logger = logging.getLogger(__name__)


@dataclass
class SuppliersState:
    query: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    sort_field: str = "name"
    sort_desc: bool = False
    loading: bool = False
    error: str = ""

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    async def submit(self, q: str) -> None:
        self.query = q
        self.page = 1
        await self.fetch()

    async def on_pagination(self, e) -> None:
        pag = e.args if isinstance(e.args, dict) else e.args[0]
        self.page = pag.get("page", 1)
        self.per_page = pag.get("rowsPerPage", 20)
        self.sort_field = pag.get("sortBy") or self.sort_field
        self.sort_desc = bool(pag.get("descending", False))
        await self.fetch()

    async def fetch(self) -> None:
        self.loading = True
        self.error = ""
        view.refresh()
        try:
            args: dict[str, Any] = {
                "limit": self.per_page, "offset": self.offset,
                "sort_by": self.sort_field if self.sort_field in ("name", "contract_count", "total_value") else "name",
            }
            if self.query:
                if self.query.isdigit():
                    args["ico"] = self.query
                else:
                    args["name_query"] = self.query
            data = await mcp_client.call_tool("find_supplier", args)
            self.rows = data.get("items", [])
            self.total = data.get("total", 0)
        except Exception as exc:  # noqa: BLE001
            logger.error("suppliers fetch failed: %s", exc)
            self.error = f"Chyba pri vyhľadávaní: {exc}"
            self.rows = []; self.total = 0
        finally:
            self.loading = False
            view.refresh()


_state = SuppliersState()


@ui.refreshable
def view() -> None:
    with ui.column().classes("w-full gap-4"):
        ui.label("Dodavatelia").classes("text-xl font-semibold text-slate-800")
        search_box(types=["supplier"], on_submit=_state.submit,
                   on_select=lambda i: _state.submit(i.get("label", "")))
        if _state.error:
            ui.label(_state.error).classes("text-red-600 text-sm")

        columns = [
            {"name": "name", "label": "Názov", "field": "name", "sortable": True, "align": "left"},
            {"name": "ico", "label": "IČO", "field": "ico", "sortable": False, "align": "left"},
            {"name": "contract_count", "label": "Počet zákaziek",
             "field": "contract_count", "sortable": True, "align": "right"},
            {"name": "total_value", "label": "Celková hodnota €",
             "field": "total_value", "sortable": True, "align": "right"},
        ]
        table = ui.table(
            columns=columns,
            rows=_state.rows,
            row_key="ico",
            pagination={
                "rowsPerPage": _state.per_page,
                "page": _state.page,
                "rowsNumber": _state.total,
                "sortBy": _state.sort_field,
                "descending": _state.sort_desc,
            },
        ).props("flat bordered").classes("w-full")
        table.on("request", lambda e: asyncio.ensure_future(_state.on_pagination(e)))

        if _state.loading:
            ui.spinner(size="md").classes("self-center")


@ui.page("/suppliers")
async def suppliers_page() -> None:
    with layout(current_path="/suppliers"):
        view()
        await _state.fetch()
```

- [ ] **Step 2: Update tests**

Replace `tests/gui/test_suppliers_page.py` with:

```python
from unittest.mock import AsyncMock

import pytest
from nicegui.testing import User


@pytest.mark.asyncio
async def test_lists_suppliers_on_open(user: User, monkeypatch):
    mock = AsyncMock(return_value={
        "items": [{"_id": "s1", "name": "Firma X", "ico": "222",
                    "contract_count": 2, "total_value": 25000}],
        "total": 1,
    })
    monkeypatch.setattr("uvo_gui.pages.suppliers.mcp_client.call_tool", mock)
    await user.open("/suppliers")
    await user.should_see("Firma X")
    await user.should_see("222")
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/gui/test_suppliers_page.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/uvo_gui/pages/suppliers.py tests/gui/test_suppliers_page.py
git commit -m "feat(gui): rework suppliers page with search_box and ui.table"
```

---

## Task 14: Graph page

**Files:**
- Create: `src/uvo_gui/static/graph_render.js`
- Create: `src/uvo_gui/pages/graph.py`
- Modify: `src/uvo_gui/app.py` — register page + static mount
- Modify: `src/uvo_gui/components/layout.py` — add nav entry
- Create: `tests/gui/test_graph_page.py`

- [ ] **Step 1: Add nav entry**

In [src/uvo_gui/components/layout.py:8-13](src/uvo_gui/components/layout.py#L8-L13), change `NAV_ITEMS` to:

```python
NAV_ITEMS = [
    ("🔍", "Vyhľadávanie", "/"),
    ("🏢", "Obstaravatelia", "/procurers"),
    ("🤝", "Dodavatelia", "/suppliers"),
    ("🕸️", "Sieť", "/graph"),
    ("ℹ️", "O aplikácii", "/about"),
]
```

- [ ] **Step 2: Write JS helper**

Create `src/uvo_gui/static/graph_render.js`:

```js
window.renderGraph = function (elId, payload) {
  if (!window.vis || !window.vis.Network) return;
  const container = document.getElementById(elId);
  if (!container) return;
  const colorFor = (type) => type === 'procurer' ? '#1d4ed8' : '#059669';
  const nodes = new vis.DataSet(payload.nodes.map(n => ({
    id: n.id, label: n.label,
    color: colorFor(n.type),
    value: Math.max(1, n.value || 1),
    font: { color: '#fff' },
  })));
  const edges = new vis.DataSet(payload.edges.map(e => ({
    from: e.from, to: e.to, label: e.label,
    value: Math.max(1, e.value || 1),
  })));
  const network = new vis.Network(container, { nodes, edges }, {
    nodes: { shape: 'dot', scaling: { min: 8, max: 32 } },
    edges: { scaling: { min: 1, max: 6 }, smooth: false, font: { size: 10 } },
    physics: { stabilization: true },
  });
  network.on('click', (params) => {
    if (params.nodes.length) {
      const id = params.nodes[0];
      window.location.href = '/procurer/' + id;
    }
  });
};
```

(The `/procurer/:ico` route is a future enhancement; for MVP a click toast is fine — but keep the handler.)

- [ ] **Step 3: Write the page**

Create `src/uvo_gui/pages/graph.py`:

```python
"""Relationship-network page with ego and CPV sub-tabs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from nicegui import ui

from uvo_gui import mcp_client
from uvo_gui.components.layout import layout
from uvo_gui.components.search_box import search_box

logger = logging.getLogger(__name__)


@dataclass
class GraphState:
    mode: str = "ego"  # or "cpv"
    ico: str = ""
    max_hops: int = 2
    cpv_code: str = ""
    year: int = field(default_factory=lambda: datetime.utcnow().year - 1)
    payload: dict[str, Any] = field(default_factory=lambda: {"nodes": [], "edges": []})
    loading: bool = False
    error: str = ""

    async def load(self) -> None:
        self.loading = True
        self.error = ""
        view.refresh()
        try:
            if self.mode == "ego":
                if not self.ico:
                    self.payload = {"nodes": [], "edges": []}
                else:
                    self.payload = await mcp_client.call_tool(
                        "graph_ego_network", {"ico": self.ico, "max_hops": self.max_hops}
                    )
            else:
                if not self.cpv_code:
                    self.payload = {"nodes": [], "edges": []}
                else:
                    self.payload = await mcp_client.call_tool(
                        "graph_cpv_network", {"cpv_code": self.cpv_code, "year": self.year}
                    )
        except Exception as exc:  # noqa: BLE001
            logger.error("graph fetch failed: %s", exc)
            self.error = f"Chyba: {exc}"
            self.payload = {"nodes": [], "edges": []}
        finally:
            self.loading = False
            view.refresh()
            await self.render()

    async def render(self) -> None:
        js = f"renderGraph('graph-canvas', {json.dumps(self.payload)});"
        ui.run_javascript(js)


_state = GraphState()


async def _on_select_entity(item: dict) -> None:
    _state.ico = item.get("id", "")
    await _state.load()


@ui.refreshable
def view() -> None:
    with ui.column().classes("w-full h-full gap-2"):
        ui.label("Sieť vzťahov").classes("text-xl font-semibold text-slate-800")
        with ui.tabs().classes("w-full") as tabs:
            ego = ui.tab("ego", label="Ego-sieť")
            cpv = ui.tab("cpv", label="CPV-sieť")
        with ui.tab_panels(tabs, value="ego").classes("w-full").on(
            "update:model-value", lambda e: _set_mode(e.args)
        ):
            with ui.tab_panel("ego"):
                with ui.row().classes("w-full gap-2 items-end"):
                    with ui.column().classes("flex-1"):
                        search_box(
                            types=["procurer", "supplier"],
                            on_submit=lambda q: _submit_ico_search(q),
                            on_select=_on_select_entity,
                        )
                    ui.number(label="Max. skokov", value=_state.max_hops, min=1, max=3).bind_value(
                        _state, "max_hops"
                    )
                    ui.button("Načítať", on_click=_state.load).props("no-caps").classes(
                        "bg-blue-700 text-white"
                    )
            with ui.tab_panel("cpv"):
                with ui.row().classes("w-full gap-2 items-end"):
                    ui.input(label="CPV kód", placeholder="napr. 48000000").classes(
                        "flex-1"
                    ).bind_value(_state, "cpv_code")
                    ui.number(label="Rok", value=_state.year).bind_value(_state, "year")
                    ui.button("Načítať", on_click=_state.load).props("no-caps").classes(
                        "bg-blue-700 text-white"
                    )

        if _state.error:
            ui.label(_state.error).classes("text-red-600 text-sm")
        if _state.loading:
            ui.spinner(size="md")
        ui.html('<div id="graph-canvas" style="width:100%;height:600px;border:1px solid #e2e8f0;border-radius:6px;"></div>')


def _set_mode(mode: str) -> None:
    _state.mode = mode
    _state.payload = {"nodes": [], "edges": []}
    view.refresh()


async def _submit_ico_search(q: str) -> None:
    # plain text query — user typed a name; no-op unless selected via autocomplete.
    # Keep empty; selection handler already sets ico.
    return


@ui.page("/graph")
async def graph_page() -> None:
    ui.add_head_html(
        '<script src="https://unpkg.com/vis-network@9/standalone/umd/vis-network.min.js"></script>'
    )
    ui.add_body_html('<script src="/static/graph_render.js"></script>')
    with layout(current_path="/graph"):
        view()
```

- [ ] **Step 4: Register page and static mount in `src/uvo_gui/app.py`**

Check the existing file and add:

```python
from pathlib import Path

from nicegui import app as nicegui_app

import uvo_gui.pages.graph  # noqa: F401  # registers /graph

nicegui_app.add_static_files("/static", str(Path(__file__).parent / "static"))
```

(Place these alongside the other page imports in `app.py`.)

- [ ] **Step 5: Write smoke test**

```python
# tests/gui/test_graph_page.py
from unittest.mock import AsyncMock

import pytest
from nicegui.testing import User


@pytest.mark.asyncio
async def test_graph_page_renders(user: User, monkeypatch):
    mock = AsyncMock(return_value={"nodes": [], "edges": []})
    monkeypatch.setattr("uvo_gui.pages.graph.mcp_client.call_tool", mock)
    await user.open("/graph")
    await user.should_see("Sieť vzťahov")
    await user.should_see("Ego-sieť")
    await user.should_see("CPV-sieť")
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/gui/test_graph_page.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/uvo_gui/pages/graph.py src/uvo_gui/static/graph_render.js src/uvo_gui/app.py src/uvo_gui/components/layout.py tests/gui/test_graph_page.py
git commit -m "feat(gui): add relationship-network page with vis-network"
```

---

## Task 15: Full-suite check + README note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full test split per CLAUDE.md**

```bash
uv run pytest tests/gui/ -v
uv run pytest tests/mcp/ -v
```

Expected: all PASS. Fix any regressions inline.

- [ ] **Step 2: Append README section**

Add a new sub-section under "Architecture" in `README.md`:

```markdown
### Search stack

Search uses **MongoDB Atlas Local** (`mongodb/mongodb-atlas-local` image) which ships
with `mongot`, Atlas Search's engine. A `sk_folding` custom analyzer (standard
tokenizer + `lowercase` + `icuFolding`) is applied to text fields on procurers,
suppliers, and notices, so queries are case- and diacritic-insensitive.

Supported query patterns in the GUI search box:

- plain words — fuzzy match via autocomplete + full-text scoring
- `"exact phrase"` — phrase match
- `fak*`, `fak?lta` — wildcard match

### Relationship graph

The `/graph` page renders procurer–supplier networks pulled from Neo4j via
`graph_ego_network` and `graph_cpv_network` MCP tools. Rendering uses
`vis-network` loaded from CDN.

### Migrating legacy data

After the image swap, run `scripts/migrate_to_atlas_local.sh` once to copy
existing data; the MCP server creates Atlas Search indexes on startup.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document atlas search stack and graph tab"
```

---

## Self-review

**Spec coverage:**

- Atlas Local swap → Task 1 ✓
- Migration script → Task 2 ✓
- Search indexes (procurers, suppliers, notices) with `sk_folding` + autocomplete + ico token + date facet → Task 3 ✓
- Index provisioning at lifespan → Task 4 ✓
- `build_search_stage` query builder with all four branches → Task 5 ✓
- Rewrite `find_procurer`/`find_supplier` + `sort_by` + `$lookup` stats → Task 6 ✓
- Rewrite `search_completed_procurements` → Task 7 ✓
- `search_autocomplete` tool → Task 8 ✓
- Reshape graph tools to `{nodes, edges}` + new `graph_ego_network` / `graph_cpv_network` → Task 9 ✓
- `search_box` component → Task 10 ✓
- Reworked search / procurers / suppliers pages with `ui.table` → Tasks 11, 12, 13 ✓
- New graph page with ego + CPV tabs, vis-network embed, nav entry → Task 14 ✓
- README + migration doc → Task 15 ✓

**Placeholder scan:** None. All code blocks complete. The `/procurer/:ico` route is flagged as future enhancement in Task 14 Step 2 and doesn't block rendering.

**Type consistency:**

- Backend tools return `{"items": [...], "total": ..., "limit": ..., "offset": ...}` consistently (Tasks 6, 7 — note: renamed `data` → `items` in Task 7 to match what the GUI already reads).
- Autocomplete result item shape `{type, id, label, sublabel}` matches `search_box` consumer (Tasks 8, 10).
- Graph payload `{nodes:[{id,label,type,value}], edges:[{from,to,label,value}]}` matches `renderGraph` JS (Tasks 9, 14).
- `sort_by` accepts `"name" | "contract_count" | "total_value"` and pages pass exactly those values (Tasks 6, 12, 13).

No inconsistencies found.
