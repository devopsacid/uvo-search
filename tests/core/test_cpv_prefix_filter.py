"""CPV filter semantics: short digit strings are prefixes, full codes stay exact.

A CPV division (``45``) is what the analytics CPV page counts (anchored regex on
``cpv_code``), so the contracts list behind that drill-down must use the same rule.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_core.adapters.mongo.procurements import (
    _find_filter,
    _search_filters,
    search_procurements,
    split_cpv,
)
from uvo_core.testing import InMemoryNoticeRepository

_KW = {
    "procurer_id": None,
    "supplier_ico": None,
    "date_from": None,
    "date_to": None,
    "value_expr": None,
}


@pytest.mark.parametrize(
    ("codes", "exact", "prefixes"),
    [
        (["45"], [], ["45"]),
        (["4523"], [], ["4523"]),
        (["4523314"], [], ["4523314"]),
        (["45000000"], ["45000000"], []),
        (["45000000-7"], ["45000000-7"], []),
        (["72000000-5", "45"], ["72000000-5"], ["45"]),
        (["4"], ["4"], []),  # too short for a division: exact (matches nothing), never a regex
        (["45.*"], ["45.*"], []),  # regex metacharacters are never promoted to a prefix
        (["(?i)4"], ["(?i)4"], []),
    ],
)
def test_split_cpv(codes, exact, prefixes):
    assert split_cpv(codes) == (exact, prefixes)


def test_find_filter_prefix_is_anchored_regex_like_analytics():
    f = _find_filter(cpv_codes=["45"], **_KW)
    assert f["cpv_code"] == {"$regex": "^45"}


def test_find_filter_exact_only_keeps_in():
    f = _find_filter(cpv_codes=["45000000-7"], **_KW)
    assert f["cpv_code"] == {"$in": ["45000000-7"]}


def test_find_filter_mixed_uses_or():
    f = _find_filter(cpv_codes=["45000000-7", "71", "72"], **_KW)
    assert "cpv_code" not in f
    assert f["$or"] == [
        {"cpv_code": {"$in": ["45000000-7"]}},
        {"cpv_code": {"$regex": "^(?:71|72)"}},
    ]


def _clauses(codes):
    return _search_filters(
        cpv_codes=codes, procurer_id=None, supplier_ico=None, date_from=None, date_to=None
    )[1:]


def test_search_filter_prefix_becomes_token_range():
    assert _clauses(["45"]) == [{"range": {"path": "cpv_code", "gte": "45", "lt": "46"}}]
    assert _clauses(["49"]) == [{"range": {"path": "cpv_code", "gte": "49", "lt": "4:"}}]


def test_search_filter_exact_keeps_in():
    assert _clauses(["45000000-7"]) == [{"in": {"path": "cpv_code", "value": ["45000000-7"]}}]


def test_search_filter_mixed_is_should_group():
    (clause,) = _clauses(["45000000-7", "71"])
    assert clause == {
        "compound": {
            "should": [
                {"in": {"path": "cpv_code", "value": ["45000000-7"]}},
                {"range": {"path": "cpv_code", "gte": "71", "lt": "72"}},
            ],
            "minimumShouldMatch": 1,
        }
    }


async def test_search_procurements_find_path_uses_prefix_regex():
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.skip.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=[])
    db = MagicMock()
    db.notices.find = MagicMock(return_value=cur)
    db.notices.count_documents = AsyncMock(return_value=0)
    search_procurements.cache_clear()

    await search_procurements(db, cpv_codes=["45"])

    filter_, _ = db.notices.find.call_args.args
    assert filter_["cpv_code"] == {"$regex": "^45"}
    db.notices.count_documents.assert_awaited_once_with(filter_)


async def test_in_memory_repository_matches_prefix_and_exact():
    notices = [
        {"_id": "a", "cpv_code": "45233140-2"},
        {"_id": "b", "cpv_code": "45000000"},
        {"_id": "c", "cpv_code": "72000000-5"},
    ]
    repo = InMemoryNoticeRepository(notices)
    assert (await repo.search(cpv_codes=["45"]))["total"] == 2
    assert (await repo.search(cpv_codes=["72000000-5"]))["total"] == 1
    assert (await repo.search(cpv_codes=["4"]))["total"] == 0
