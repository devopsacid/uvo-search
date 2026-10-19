"""``/api/analytics/*`` endpoints against the in-memory D1 reference implementation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ExecutionTimeout

from tests.api._deps import deps
from uvo_api.app import create_app
from uvo_api.db import get_dashboard_analytics
from uvo_core.testing import InMemoryDashboardAnalytics

FIXTURE = Path(__file__).parent.parent / "fixtures" / "analytics_notices.json"
RANGE = {"date_from": "2023-01-01", "date_to": "2025-12-31"}

META_KEYS = {"definition", "filters", "generated_at"}
FILTER_KEYS = {"date_from", "date_to", "cpv", "source", "procurer_ico", "supplier_ico"}
PERIOD_KEYS = {
    "date_from",
    "date_to",
    "contract_count",
    "total_value",
    "avg_value",
    "procurer_count",
    "supplier_count",
}
POINT_KEYS = {"period", "contract_count", "total_value", "avg_value"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    return TestClient(create_app())


@pytest.fixture
def fake():
    return InMemoryDashboardAnalytics(json.loads(FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture
def get(client, fake):
    def _get(path: str, **params):
        with deps(client, get_dashboard_analytics, fake):
            return client.get(f"/api/analytics{path}", params=params)

    return _get


def test_summary_shape_and_meta_echo(get):
    response = get("/summary", **RANGE, source="crz")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"meta", "current", "previous", "deltas"}
    assert set(body["meta"]) == META_KEYS and body["meta"]["definition"] == "D1"
    assert body["meta"]["filters"] == {**{k: None for k in FILTER_KEYS}, **RANGE, "source": "crz"}
    assert body["meta"]["generated_at"].endswith("Z")
    assert set(body["current"]) == PERIOD_KEYS
    assert set(body["deltas"]) == {
        "contract_count_pct",
        "total_value_pct",
        "avg_value_pct",
        "procurer_count_pct",
        "supplier_count_pct",
    }
    assert body["current"]["contract_count"] == 6
    assert body["previous"] is not None


def test_summary_without_params_uses_default_period(get):
    body = get("/summary").json()
    filters = body["meta"]["filters"]
    assert filters["date_from"].endswith("-01-01") and filters["date_to"]
    assert int(filters["date_to"][:4]) - int(filters["date_from"][:4]) == 4


def test_timeseries_shape(get):
    body = get("/timeseries", **RANGE, granularity="quarter").json()
    assert set(body) == {"meta", "granularity", "points", "series"}
    assert body["granularity"] == "quarter" and body["series"] is None
    assert set(body["points"][0]) == POINT_KEYS
    assert body["points"][0]["period"] == "2023-Q1" and len(body["points"]) == 12


def test_timeseries_defaults_to_monthly(get):
    assert get("/timeseries", **RANGE).json()["granularity"] == "month"


def test_timeseries_split_by_returns_series(get):
    body = get("/timeseries", **RANGE, split_by="cpv_division", top=2).json()
    keys = [s["key"] for s in body["series"]]
    assert len(keys) == 3 and keys[-1] == "other"
    assert set(body["series"][0]) == {"key", "label", "points"}
    assert set(body["series"][0]["points"][0]) == POINT_KEYS


def test_top_shape(get):
    body = get("/top", **RANGE, dimension="supplier", n=3).json()
    assert set(body) == {"meta", "dimension", "metric", "total", "items", "other"}
    assert body["metric"] == "total_value" and len(body["items"]) == 3
    assert set(body["items"][0]) == {
        "key",
        "label",
        "ico",
        "total_value",
        "contract_count",
        "share_pct",
    }
    assert set(body["total"]) == {"total_value", "contract_count"}
    assert set(body["other"]) == {"total_value", "contract_count", "share_pct"}


def test_top_cpv_division_has_null_ico(get):
    body = get("/top", **RANGE, dimension="cpv_division", metric="contract_count").json()
    assert body["items"][0]["ico"] is None


def test_concentration_shape(get):
    body = get("/concentration", **RANGE).json()
    assert set(body) == {
        "meta",
        "dimension",
        "hhi",
        "hhi_band",
        "cr4_pct",
        "cr10_pct",
        "entity_count",
        "total_value",
        "top",
    }
    assert body["dimension"] == "supplier" and body["hhi_band"] == "high"
    assert set(body["top"][0]) == {"ico", "name", "total_value", "share_pct", "cumulative_pct"}


def test_concentration_empty_selection_is_low_zero(get):
    body = get("/concentration", date_from="2000-01-01", date_to="2000-12-31").json()
    assert body["hhi"] == 0 and body["hhi_band"] == "low" and body["entity_count"] == 0


def test_cpv_shape(get):
    body = get("/cpv", **RANGE, level="group").json()
    assert set(body) == {"meta", "level", "total_value", "contract_count", "items"}
    assert set(body["items"][0]) == {
        "cpv_code",
        "prefix",
        "label_sk",
        "total_value",
        "contract_count",
        "share_pct",
    }
    assert body["level"] == "group"


def test_coverage_shape_and_ignores_common_filters(get):
    body = get("/coverage", source="crz", cpv="45").json()
    assert set(body) == {"generated_at", "sources", "monthly", "canonical"}
    assert [s["source"] for s in body["sources"]] == ["vestnik", "crz", "ted", "uvo", "itms"]
    assert set(body["sources"][0]) == {
        "source",
        "notices_total",
        "contract_awards",
        "last_publication_date",
        "last_ingested_at",
        "age_seconds",
        "status",
        "expected_cadence_seconds",
        "quality",
    }
    assert set(body["sources"][0]["quality"]) == {
        "with_value_pct",
        "with_cpv_pct",
        "with_supplier_ico_pct",
        "with_procurer_ico_pct",
    }
    assert set(body["monthly"][0]) == {"period", "vestnik", "crz", "ted", "uvo", "itms"}
    assert set(body["canonical"]) == {"notices_with_canonical_id", "match_groups"}


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/summary", {"date_from": "2025-02-01", "date_to": "2025-01-01"}),
        ("/summary", {"date_from": "2005-01-01", "date_to": "2026-01-01"}),
        ("/summary", {"date_from": "not-a-date"}),
        ("/summary", {"cpv": "4"}),
        ("/summary", {"source": "sap"}),
        ("/summary", {"procurer_ico": "abc"}),
        ("/summary", {"supplier_ico": "1234567890123"}),
        ("/timeseries", {"granularity": "week"}),
        ("/timeseries", {"split_by": "procurer"}),
        ("/timeseries", {"split_by": "source", "top": 11}),
        ("/timeseries", {"split_by": "source", "top": 0}),
        ("/top", {}),
        ("/top", {"dimension": "country"}),
        ("/top", {"dimension": "supplier", "metric": "profit"}),
        ("/top", {"dimension": "supplier", "n": 51}),
        ("/top", {"dimension": "supplier", "n": 0}),
        ("/concentration", {"dimension": "cpv_division"}),
        ("/cpv", {"level": "class"}),
    ],
)
def test_validation_errors_are_422(get, path, params):
    response = get(path, **params)
    assert response.status_code == 422, response.text
    assert "detail" in response.json()


def test_filter_validation_error_names_the_parameter(get):
    detail = get("/summary", cpv="x").json()["detail"]
    assert detail[0]["loc"] == ["query", "cpv"]


@pytest.mark.parametrize(
    ("path", "method", "params"),
    [
        ("/summary", "summary", {}),
        ("/timeseries", "timeseries", {}),
        ("/top", "top", {"dimension": "supplier"}),
        ("/concentration", "concentration", {}),
        ("/cpv", "cpv", {}),
        ("/coverage", "coverage", {}),
    ],
)
def test_aggregate_timeout_is_504(client, path, method, params):
    stub = AsyncMock()
    getattr(stub, method).side_effect = ExecutionTimeout("operation exceeded time limit")
    with deps(client, get_dashboard_analytics, stub):
        response = client.get(f"/api/analytics{path}", params=params)
    assert response.status_code == 504
    assert response.json() == {"detail": "analytics_timeout"}


def test_backend_outage_is_still_503(client):
    from uvo_core.errors import BackendUnavailable

    stub = AsyncMock()
    stub.summary.side_effect = BackendUnavailable("mongo down")
    with deps(client, get_dashboard_analytics, stub):
        response = client.get("/api/analytics/summary")
    assert response.status_code == 503


def test_openapi_documents_all_six_endpoints(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    monkeypatch.setenv("API_DOCS_ENABLED", "true")
    from uvo_api.config import get_settings

    get_settings.cache_clear()
    try:
        spec = TestClient(create_app()).get("/openapi.json").json()
    finally:
        get_settings.cache_clear()
    paths = {p for p in spec["paths"] if p.startswith("/api/analytics")}
    assert paths == {
        "/api/analytics/summary",
        "/api/analytics/timeseries",
        "/api/analytics/top",
        "/api/analytics/concentration",
        "/api/analytics/cpv",
        "/api/analytics/coverage",
    }
    assert all(list(spec["paths"][p]) == ["get"] for p in paths)


async def test_lifespan_warmup_is_best_effort(monkeypatch):
    from unittest.mock import MagicMock

    from uvo_api import app as app_module

    seen = []

    async def boom(analytics):
        seen.append(analytics)
        raise RuntimeError("mongo is gone")

    monkeypatch.setattr(app_module, "warm_default_dashboards", boom)
    await app_module._warm_dashboards(MagicMock(), delay=0)  # must not raise
    assert len(seen) == 1
