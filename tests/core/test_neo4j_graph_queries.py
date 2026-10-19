"""Cypher text/parameter tests for uvo_core.adapters.neo4j.graph (B5, B6, B7)."""

from unittest.mock import MagicMock

from uvo_core.adapters.neo4j import graph


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r

        return gen()

    async def single(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, calls, rows_by_call):
        self._calls = calls
        self._rows_by_call = rows_by_call

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query, parameters=None, **params):
        text = getattr(query, "text", query)
        self._calls.append({"text": text, "timeout": getattr(query, "timeout", None), **params})
        idx = len(self._calls) - 1
        rows = self._rows_by_call[idx] if idx < len(self._rows_by_call) else []
        return _FakeResult(rows)


def _driver(rows_by_call=()):
    calls: list[dict] = []
    driver = MagicMock()
    driver.session = lambda *a, **k: _FakeSession(calls, list(rows_by_call))
    return driver, calls


async def test_related_organisations_interpolates_clamped_hops():
    driver, calls = _driver()
    await graph.related_organisations(driver, "123", max_hops=99)
    text = calls[0]["text"]
    assert "$max_hops" not in text
    assert "*1..4" in text
    assert "max_hops" not in calls[0]


async def test_ego_network_is_labelled_bounded_and_has_timeout():
    start = {"name": "A", "ico": "1", "type": "Procurer", "contract_count": 3}
    driver, calls = _driver([[start]])
    await graph.ego_network(driver, "1", max_hops=10)
    expand = calls[1]
    text = expand["text"]
    assert "MATCH (a {" not in text  # no unlabelled anchor
    assert "Procurer|Supplier" in text
    assert "*1..2" in text  # hops capped at 2
    assert "ISSUED|AWARDED_TO" in text
    assert "LIMIT $limit" in text
    assert expand["limit"] == 50
    assert expand["timeout"] is not None


async def test_ego_network_default_hops_is_two():
    start = {"name": "A", "ico": "1", "type": "Supplier", "contract_count": 1}
    driver, calls = _driver([[start]])
    await graph.ego_network(driver, "1")
    assert "*1..2" in calls[1]["text"]


async def test_ego_network_total_value_uses_head_not_list_index():
    start = {"name": "A", "ico": "1", "type": "Supplier", "contract_count": 1}
    driver, calls = _driver([[start]])
    await graph.ego_network(driver, "1")
    assert "head([" in calls[1]["text"]
    assert "][0]" not in calls[1]["text"]


async def test_cpv_network_uses_date_range_not_year_accessor():
    driver, calls = _driver()
    await graph.cpv_network(driver, "72000000-5", 2024)
    text = calls[0]["text"]
    assert ".year" not in text
    assert "n.publication_date >= date($start)" in text
    assert "n.publication_date < date($end)" in text
    assert calls[0]["start"] == "2024-01-01"
    assert calls[0]["end"] == "2025-01-01"


async def test_procurement_network_uses_date_range():
    driver, calls = _driver()
    await graph.procurement_network(driver, "72000000-5", 2024)
    assert ".year" not in calls[0]["text"]
    assert calls[0]["start"] == "2024-01-01"
