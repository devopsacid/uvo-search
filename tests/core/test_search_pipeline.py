"""Shape tests for the Atlas Search hot path (plan W3: B3, B13, B22).

These pin the *generated* Mongo queries, not results: no database is involved.

- B3: filters live inside ``$search`` as non-scoring ``compound.filter`` clauses,
  ordering comes from ``$search.sort`` and the total from ``$searchMeta`` — so no
  stage sorts or counts the whole corpus in memory. An empty text query skips
  Atlas Search and uses an indexed ``find().sort()``.
- B13: list paths project away fields no list view reads.
- B22: empty-query entity listing uses an indexed ``find().sort()``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_core.adapters.mongo.procurements import NOTICE_LIST_PROJECTION, search_procurements
from uvo_core.adapters.mongo.search_query import build_search_stage, with_filters
from uvo_core.adapters.mongo.subjects import ENTITY_LIST_PROJECTION, entity_search

NOTICE_PATHS = ["title", "description", "procurer.name", "awards.supplier.name"]


@pytest.fixture(autouse=True)
def _clear_caches():
    search_procurements.cache_clear()
    entity_search.cache_clear()
    yield
    search_procurements.cache_clear()
    entity_search.cache_clear()


def _cursor(docs: list[dict]) -> MagicMock:
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.skip.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=docs)
    return cur


def _agg(result: list[dict]) -> MagicMock:
    agg = MagicMock()
    agg.to_list = AsyncMock(return_value=result)
    return agg


def _notices_db(*aggregate_results: list[dict]) -> MagicMock:
    db = MagicMock()
    db.notices.aggregate = MagicMock(side_effect=[_agg(r) for r in aggregate_results])
    return db


# --------------------------------------------------------------------------- helper


def test_with_filters_wraps_operator_in_compound_must():
    op = build_search_stage("košice", ["title"])
    filters = [{"equals": {"path": "notice_type", "value": "contract_award"}}]
    assert with_filters(op, filters) == {"compound": {"must": [op], "filter": filters}}


def test_with_filters_without_filters_returns_operator_unchanged():
    op = build_search_stage("košice", ["title"])
    assert with_filters(op, []) is op


# --------------------------------------------------------------- procurements: no text


async def test_empty_text_query_uses_indexed_find_not_search():
    cur = _cursor([{"_id": 1, "title": "A"}])
    db = MagicMock()
    db.notices.find = MagicMock(return_value=cur)
    db.notices.count_documents = AsyncMock(return_value=42)
    db.notices.aggregate = MagicMock()

    out = await search_procurements(
        db, text_query="  ", date_from="2024-01-01", date_to="2024-12-31", limit=10, offset=20
    )

    db.notices.aggregate.assert_not_called()
    filter_, projection = db.notices.find.call_args.args
    assert filter_ == {
        "notice_type": "contract_award",
        "publication_date": {"$gte": "2024-01-01", "$lte": "2024-12-31"},
    }
    assert projection == NOTICE_LIST_PROJECTION
    cur.sort.assert_called_once_with([("publication_date", -1)])
    cur.skip.assert_called_once_with(20)
    cur.limit.assert_called_once_with(10)
    db.notices.count_documents.assert_awaited_once_with(filter_)
    assert out == {"items": [{"_id": "1", "title": "A"}], "total": 42, "limit": 10, "offset": 20}


async def test_empty_text_query_value_filter_goes_into_find_filter():
    db = MagicMock()
    db.notices.find = MagicMock(return_value=_cursor([]))
    db.notices.count_documents = AsyncMock(return_value=0)

    await search_procurements(db, value_min=100, value_max=500, cpv_codes=["72000000-5"])

    filter_, _ = db.notices.find.call_args.args
    assert filter_["cpv_code"] == {"$in": ["72000000-5"]}
    conds = filter_["$expr"]["$and"]
    coalesced = {"$ifNull": ["$final_value", {"$ifNull": ["$estimated_value", 0]}]}
    assert conds == [{"$gte": [coalesced, 100]}, {"$lte": [coalesced, 500]}]


# ------------------------------------------------------------- procurements: text query


async def test_text_query_pushes_filters_sort_and_count_into_atlas_search():
    db = _notices_db(
        [{"_id": "n1", "title": "Košice"}],
        [{"count": {"total": 7}}],
    )

    out = await search_procurements(
        db,
        text_query="kosice",
        cpv_codes=["45000000-7"],
        procurer_id="00151742",
        supplier_ico="35763469",
        date_from="2024-01-01",
        date_to="2024-12-31",
        limit=5,
        offset=10,
    )

    items_pipeline = db.notices.aggregate.call_args_list[0].args[0]
    count_pipeline = db.notices.aggregate.call_args_list[1].args[0]

    search = items_pipeline[0]["$search"]
    assert search["index"] == "default"
    assert search["sort"] == {"publication_date": -1}
    compound = search["compound"]
    # Text operator unchanged → sk_folding / fuzzy / autocomplete behaviour preserved.
    assert compound["must"] == [build_search_stage("kosice", NOTICE_PATHS)]
    assert compound["filter"] == [
        {"equals": {"path": "notice_type", "value": "contract_award"}},
        {"in": {"path": "cpv_code", "value": ["45000000-7"]}},
        {"equals": {"path": "procurer.ico", "value": "00151742"}},
        {"equals": {"path": "awards.supplier.ico", "value": "35763469"}},
        {"range": {"path": "publication_date", "gte": "2024-01-01", "lte": "2024-12-31"}},
    ]
    # No in-memory corpus stages any more.
    assert not any("$facet" in s or "$sort" in s or "$match" in s for s in items_pipeline)
    assert items_pipeline[1:] == [
        {"$skip": 10},
        {"$limit": 5},
        {"$project": NOTICE_LIST_PROJECTION},
    ]

    # Count is answered by mongot alone, over the same operator.
    assert count_pipeline == [
        {
            "$searchMeta": {
                "index": "default",
                "compound": compound,
                "count": {"type": "total"},
            }
        }
    ]
    assert out == {
        "items": [{"_id": "n1", "title": "Košice"}],
        "total": 7,
        "limit": 5,
        "offset": 10,
    }


async def test_text_query_only_date_from_emits_open_range():
    db = _notices_db([], [{"count": {"total": 0}}])
    await search_procurements(db, text_query="fakulta", date_from="2024-01-01")
    compound = db.notices.aggregate.call_args_list[0].args[0][0]["$search"]["compound"]
    assert compound["filter"] == [
        {"equals": {"path": "notice_type", "value": "contract_award"}},
        {"range": {"path": "publication_date", "gte": "2024-01-01"}},
    ]


async def test_text_query_with_value_filter_streams_match_after_search():
    """The coalesced contract value can't be expressed in $search, so it stays a
    $match — but after a sorted $search, before $skip/$limit, so the page is
    produced by streaming instead of sorting the matched set in memory."""
    db = _notices_db([{"_id": "n1"}], [{"count": 3}])

    out = await search_procurements(db, text_query="it", value_min=1000)

    items_pipeline = db.notices.aggregate.call_args_list[0].args[0]
    count_pipeline = db.notices.aggregate.call_args_list[1].args[0]
    value_match = {
        "$match": {
            "$expr": {
                "$gte": [
                    {"$ifNull": ["$final_value", {"$ifNull": ["$estimated_value", 0]}]},
                    1000,
                ]
            }
        }
    }
    assert items_pipeline[0]["$search"]["sort"] == {"publication_date": -1}
    assert items_pipeline[1:] == [
        value_match,
        {"$skip": 0},
        {"$limit": 20},
        {"$project": NOTICE_LIST_PROJECTION},
    ]
    assert "sort" not in count_pipeline[0]["$search"]
    assert count_pipeline[1:] == [value_match, {"$count": "count"}]
    assert out["total"] == 3


async def test_text_query_empty_count_result_means_zero():
    db = _notices_db([], [])
    out = await search_procurements(db, text_query="nonexistent")
    assert out["total"] == 0
    assert out["items"] == []


def test_list_projection_drops_heavy_fields_but_keeps_row_fields():
    assert NOTICE_LIST_PROJECTION["description"] == 0
    assert NOTICE_LIST_PROJECTION["attachments"] == 0
    # Fields read by uvo_api._schema.map_contract_row / company / unified search.
    for keep in (
        "title",
        "procurer",
        "awards",
        "final_value",
        "estimated_value",
        "cpv_code",
        "publication_date",
        "award_date",
        "status",
        "source_id",
    ):
        assert keep not in NOTICE_LIST_PROJECTION
    assert set(NOTICE_LIST_PROJECTION.values()) == {0}  # exclusion-only projection


# ------------------------------------------------------------------------ entities


async def test_empty_entity_query_uses_indexed_find_sort():
    cur = _cursor([{"_id": "a", "name": "Acme", "contract_count": None}, {"_id": "b"}])
    coll = MagicMock()
    coll.find = MagicMock(return_value=cur)
    coll.estimated_document_count = AsyncMock(return_value=1234)
    coll.aggregate = MagicMock()
    db = {"suppliers": coll}

    out = await entity_search(
        db,
        "suppliers",
        "awards.supplier.ico",
        name_query="   ",
        ico=None,
        sort_by="contract_count",
        limit=2,
        offset=4,
    )

    coll.aggregate.assert_not_called()
    coll.find.assert_called_once_with({}, ENTITY_LIST_PROJECTION)
    cur.sort.assert_called_once_with([("contract_count", -1), ("_id", 1)])
    cur.skip.assert_called_once_with(4)
    cur.limit.assert_called_once_with(2)
    assert out["total"] == 1234
    # Same defaults the $ifNull stage used to apply.
    assert out["items"] == [
        {"_id": "a", "name": "Acme", "contract_count": 0, "total_value": 0},
        {"_id": "b", "contract_count": 0, "total_value": 0},
    ]


@pytest.mark.parametrize(
    ("sort_by", "spec"),
    [
        ("name", [("name", 1), ("_id", 1)]),
        ("total_value", [("total_value", -1), ("_id", 1)]),
    ],
)
async def test_empty_entity_query_sort_specs(sort_by, spec):
    cur = _cursor([])
    coll = MagicMock()
    coll.find = MagicMock(return_value=cur)
    coll.estimated_document_count = AsyncMock(return_value=0)
    await entity_search(
        {"procurers": coll},
        "procurers",
        "procurer.ico",
        name_query=None,
        ico=None,
        sort_by=sort_by,
        limit=10,
        offset=0,
    )
    cur.sort.assert_called_once_with(spec)


async def test_entity_text_query_projects_away_embeddings():
    agg = _agg([{"items": [], "total": []}])
    coll = MagicMock()
    coll.aggregate = MagicMock(return_value=agg)
    await entity_search(
        {"procurers": coll},
        "procurers",
        "procurer.ico",
        name_query="mesto košice",
        ico=None,
        sort_by="name",
        limit=10,
        offset=0,
    )
    (pipeline,) = coll.aggregate.call_args.args
    assert pipeline[0]["$search"] == {
        "index": "default",
        **build_search_stage("mesto košice", ["name"]),
    }
    assert pipeline[1] == {"$project": ENTITY_LIST_PROJECTION}


async def test_entity_ico_lookup_projects_away_embeddings():
    coll = MagicMock()
    coll.count_documents = AsyncMock(return_value=1)
    coll.find = MagicMock(return_value=_cursor([{"_id": "x", "ico": "123"}]))
    await entity_search(
        {"procurers": coll},
        "procurers",
        "procurer.ico",
        name_query=None,
        ico="123",
        sort_by="name",
        limit=1,
        offset=0,
    )
    coll.find.assert_called_once_with({"ico": "123"}, ENTITY_LIST_PROJECTION)


def test_entity_projection_drops_name_embedding():
    assert ENTITY_LIST_PROJECTION == {"name_embedding": 0}
