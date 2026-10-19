"""``/api/contracts?source=`` drill-down filter (analytics dashboards)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.api._deps import deps
from uvo_api.app import create_app
from uvo_api.db import get_notice_repo
from uvo_core.adapters.mongo.procurements import search_procurements
from uvo_core.adapters.mongo.repositories import MongoNoticeRepository
from uvo_core.cache import clear_data_caches


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_data_caches()
    yield
    clear_data_caches()


def _repo():
    repo = MagicMock()
    repo.search = AsyncMock(return_value={"items": [], "total": 0})
    return repo


def test_router_passes_source_through(client):
    repo = _repo()
    with deps(client, get_notice_repo, repo):
        response = client.get("/api/contracts?source=crz")
    assert response.status_code == 200
    assert repo.search.await_args.kwargs["source"] == "crz"


def test_router_source_defaults_to_none(client):
    repo = _repo()
    with deps(client, get_notice_repo, repo):
        client.get("/api/contracts")
    assert repo.search.await_args.kwargs["source"] is None


@pytest.mark.parametrize("value", ["sap", "CRZ", "vestnik;drop"])
def test_router_rejects_unknown_source(client, value):
    repo = _repo()
    with deps(client, get_notice_repo, repo):
        response = client.get("/api/contracts", params={"source": value})
    assert response.status_code == 422
    repo.search.assert_not_awaited()


@pytest.mark.parametrize("value", ["vestnik", "crz", "ted", "uvo", "itms"])
def test_router_accepts_every_known_source(client, value):
    repo = _repo()
    with deps(client, get_notice_repo, repo):
        assert client.get("/api/contracts", params={"source": value}).status_code == 200


def _cursor(docs):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.skip.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=docs)
    return cur


async def test_no_text_path_adds_source_to_the_find_filter():
    db = MagicMock()
    db.notices.find = MagicMock(return_value=_cursor([]))
    db.notices.count_documents = AsyncMock(return_value=0)

    await search_procurements(db, source="crz")

    filter_, _ = db.notices.find.call_args.args
    assert filter_ == {"notice_type": "contract_award", "source": "crz"}
    db.notices.count_documents.assert_awaited_once_with(filter_)


def _agg(rows):
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=rows)
    return cur


async def test_text_path_applies_source_as_match_after_search():
    db = MagicMock()
    db.notices.aggregate = MagicMock(side_effect=[_agg([{"_id": "n1"}]), _agg([{"count": 4}])])

    out = await search_procurements(db, text_query="most", source="crz")

    items = db.notices.aggregate.call_args_list[0].args[0]
    count = db.notices.aggregate.call_args_list[1].args[0]
    source_match = {"$match": {"source": "crz"}}
    assert "$search" in items[0]
    assert items[1] == source_match
    assert items[2:4] == [{"$skip": 0}, {"$limit": 20}]
    # the count can no longer come from $searchMeta: it must see the post-match
    assert "$searchMeta" not in count[0]
    assert count[1:] == [source_match, {"$count": "count"}]
    assert out["total"] == 4


async def test_text_path_without_source_keeps_search_meta_count():
    db = MagicMock()
    db.notices.aggregate = MagicMock(
        side_effect=[_agg([]), _agg([{"count": {"total": 2}}])],
    )
    await search_procurements(db, text_query="most")
    count = db.notices.aggregate.call_args_list[1].args[0]
    assert "$searchMeta" in count[0]


async def test_source_is_part_of_the_cache_key():
    db = MagicMock()
    db.notices.find = MagicMock(return_value=_cursor([]))
    db.notices.count_documents = AsyncMock(return_value=0)

    repo = MongoNoticeRepository(db)  # the repository passes every key-relevant kwarg
    await repo.search(source="crz")
    await repo.search(source="ted")
    await repo.search(source="crz")  # cached

    assert db.notices.find.call_count == 2
