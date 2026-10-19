"""E2E checks for the analytics dashboards (``/api/analytics/*``) and observability.

Runs against the compose stack (see ``conftest.py``). Contract shapes follow
spec section 6.2 (``docs/specs/2026-10-19-analytics-dashboards.md``); metric
families follow spec section 8.1.

Seeding
-------
``tests/fixtures/analytics_notices.json`` (30 notices) is upserted into the
compose Mongo only when it is safe:

- the ``notices`` collection is empty (fresh stack, e.g. CI), or
- ``E2E_SEED_FIXTURE=1`` is set explicitly.

The seeder never deletes or overwrites a notice that is not a fixture notice
(title must start with ``Fixture ``); on any clash it aborts the seed. Seeding
creates the (empty) ``procurers``/``suppliers`` collections because Atlas Search
index provisioning fails while they are missing.

Known product defects are recorded as ``xfail(strict=True)`` so the suite stays
green while they exist and fails loudly (XPASS) once they are fixed and the
marker must be removed.

Consistency checks assume a quiescent corpus: run them after the ingestor has
drained its Redis backlog (``XINFO GROUPS notices:<source>`` lag 0). While a
backlog drains, counts move between requests and cross-endpoint equality checks
fail for reasons unrelated to the code.
"""

import json
import os
import re
import subprocess
import time
from datetime import date
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = "docker-compose.yml"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "analytics_notices.json"
API = "http://localhost:8001"
MCP = "http://localhost:8000"
GUI = "http://localhost:8080"
SOURCES = {"vestnik", "crz", "ted", "uvo", "itms"}
MONGO_DB = os.environ.get("API_MONGODB_DATABASE", "uvo_search")
DEFAULT_FROM = f"{date.today().year - 4}-01-01"
DEFAULT_TO = date.today().isoformat()
ANALYTICS_PAGES = ["prehlad", "koncentracia", "cpv", "pokrytie"]

# Metric families that must be exposed (spec 8.1). Worker families are checked
# on the ingestor, which is running; extractors are not scraped in this suite.
API_FAMILIES = [
    "uvo_api_http_requests_total",
    "uvo_api_http_request_duration_seconds",
    "uvo_api_http_requests_in_progress",
    "uvo_ready",
    "uvo_build_info",
]
MCP_FAMILIES = ["uvo_ready", "uvo_cache_requests_total"]
WORKER_FAMILIES = [
    "uvo_worker_start_timestamp_seconds",
    "uvo_worker_last_error",
    "uvo_worker_info",
]


# --------------------------------------------------------------------------- helpers


def _mongo_password() -> str | None:
    """MONGO_PASSWORD from the environment, else from the repo ``.env``.

    The value is never printed or logged.
    """
    value = os.environ.get("MONGO_PASSWORD")
    if value:
        return value
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("MONGO_PASSWORD="):
                return line.partition("=")[2].strip() or None
    return None


def _compose(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _get(url: str, **kwargs) -> httpx.Response:
    return httpx.get(url, timeout=60, **kwargs)


def _get_status(url: str) -> int | None:
    try:
        return _get(url).status_code
    except httpx.HTTPError:
        return None


def _wait_status(url: str, want: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if _get(url).status_code == want:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(3)
    return False


def _seed_fixture() -> str:
    """Seed the fixture notices if safe. Returns a short status string."""
    from pymongo import MongoClient

    password = _mongo_password()
    if not password:
        return "skipped: no MONGO_PASSWORD available"

    client = MongoClient(
        "localhost",
        27017,
        username="uvo",
        password=password,
        authSource="admin",
        directConnection=True,
        serverSelectionTimeoutMS=5000,
    )
    db = client[MONGO_DB]
    docs = json.loads(FIXTURE.read_text())
    empty = db.notices.estimated_document_count() == 0
    if not empty and os.environ.get("E2E_SEED_FIXTURE") != "1":
        return "skipped: notices exist and E2E_SEED_FIXTURE!=1"

    for doc in docs:
        existing = db.notices.find_one(
            {"source": doc["source"], "source_id": doc["source_id"]}, {"title": 1}
        )
        if existing and not str(existing.get("title", "")).startswith("Fixture "):
            pytest.fail(
                f"refusing to seed: non-fixture notice {doc['source']}/{doc['source_id']} exists"
            )

    for doc in docs:
        db.notices.update_one(
            {"source": doc["source"], "source_id": doc["source_id"]},
            {"$set": doc},
            upsert=True,
        )
    existing_names = set(db.list_collection_names())
    for name in ("procurers", "suppliers"):
        if name not in existing_names:
            db.create_collection(name)
    client.close()
    return f"seeded {len(docs)} fixture notices (empty_db={empty})"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def analytics_ready(compose_stack):
    """Seed if safe, then wait for API readiness with fresh analytics caches.

    The API warms the default dashboards at startup and caches them for an hour;
    the ``notices:written`` invalidation is debounced and can drop the last event
    of a burst. After seeding the API is therefore restarted, which also provisions
    the Atlas Search indexes (they are only provisioned at startup). Returns a dict
    describing what happened; the xfail readiness test reads it.
    """
    ready_before = _get_status(f"{API}/readyz") == 200
    info: dict = {"seed": _seed_fixture(), "ready_before_seed": ready_before}
    info["recovered_without_restart"] = None
    seeded = info["seed"].startswith("seeded")
    if seeded:
        if not ready_before:
            info["recovered_without_restart"] = _wait_status(f"{API}/readyz", 200, 30)
        _compose("restart", "api", timeout=180)
    if not _wait_status(f"{API}/readyz", 200, 180):
        pytest.fail(f"API /readyz not 200 ({info})")
    return info


@pytest.fixture(scope="module")
def default_summary(analytics_ready):
    resp = _get(f"{API}/api/analytics/summary")
    assert resp.status_code == 200, resp.text
    return resp.json()


# --------------------------------------------------------------------------- readiness


class TestReadiness:
    def test_api_readyz_200(self, analytics_ready):
        resp = _get(f"{API}/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    @pytest.mark.xfail(
        strict=True,
        reason="DEFECT: API search-index provisioning is not retried after collections "
        "appear on a fresh DB; /readyz stays 503 until the API restarts.",
    )
    def test_api_readyz_recovers_without_restart(self, analytics_ready):
        if not analytics_ready["seed"].startswith("seeded") or analytics_ready["ready_before_seed"]:
            pytest.skip("API was not in a cold-start state (no fresh DB); nothing to recover from")
        assert analytics_ready["recovered_without_restart"] is True

    @pytest.mark.xfail(
        strict=True,
        reason="DEFECT: MCP /readyz reports 'no MongoDB handle' unless an MCP client "
        "session is open; the Mongo handle is set per session in app_lifespan.",
    )
    def test_mcp_readyz_without_open_session(self, compose_stack):
        assert _get(f"{MCP}/readyz").status_code == 200


# --------------------------------------------------------------------------- shapes


class TestSummary:
    def test_shape_and_definition(self, default_summary):
        d = default_summary
        assert set(d) >= {"meta", "current", "previous", "deltas"}
        assert d["meta"]["definition"] == "D1"
        assert set(d["meta"]["filters"]) == {
            "date_from",
            "date_to",
            "cpv",
            "source",
            "procurer_ico",
            "supplier_ico",
        }
        period_keys = {
            "date_from",
            "date_to",
            "contract_count",
            "total_value",
            "avg_value",
            "procurer_count",
            "supplier_count",
        }
        assert set(d["current"]) == period_keys
        assert d["previous"] is not None  # 1993+ window, so previous exists
        assert set(d["previous"]) == period_keys
        assert set(d["deltas"]) == {
            "contract_count_pct",
            "total_value_pct",
            "avg_value_pct",
            "procurer_count_pct",
            "supplier_count_pct",
        }

    def test_default_window_is_five_calendar_years(self, default_summary):
        f = default_summary["meta"]["filters"]
        assert f["date_from"] == DEFAULT_FROM
        assert f["date_to"] == DEFAULT_TO

    def test_delta_is_null_when_previous_is_zero(self):
        resp = _get(
            f"{API}/api/analytics/summary",
            params={
                "date_from": "2023-01-01",
                "date_to": "2023-12-31",
                "cpv": "45",
                "source": "vestnik",
            },
        )
        assert resp.status_code == 200
        d = resp.json()
        if d["previous"] and d["previous"]["contract_count"] == 0:
            assert d["deltas"]["contract_count_pct"] is None

    def test_previous_is_null_before_1993(self):
        resp = _get(
            f"{API}/api/analytics/summary",
            params={"date_from": "1992-01-01", "date_to": "1992-06-01"},
        )
        assert resp.status_code == 200
        assert resp.json()["previous"] is None


class TestTimeseries:
    @pytest.mark.parametrize(
        ("granularity", "expected_points"),
        [("year", 5), ("quarter", 20), ("month", 58)],
    )
    def test_zero_filled_over_default_window(self, analytics_ready, granularity, expected_points):
        resp = _get(f"{API}/api/analytics/timeseries", params={"granularity": granularity})
        assert resp.status_code == 200
        d = resp.json()
        assert d["granularity"] == granularity
        assert d["series"] is None
        assert len(d["points"]) == expected_points
        pattern = {
            "year": r"^\d{4}$",
            "quarter": r"^\d{4}-Q[1-4]$",
            "month": r"^\d{4}-\d{2}$",
        }[granularity]
        for p in d["points"]:
            assert re.match(pattern, p["period"]), p
            assert set(p) == {"period", "contract_count", "total_value", "avg_value"}

    def test_split_by_source_returns_top_series_plus_other(self, analytics_ready):
        resp = _get(
            f"{API}/api/analytics/timeseries",
            params={"granularity": "year", "split_by": "source", "top": 2},
        )
        assert resp.status_code == 200
        series = resp.json()["series"]
        keys = [s["key"] for s in series]
        assert len(keys) <= 3
        assert keys[-1] == "other"
        assert series[-1]["label"] == "Ostatné"
        assert set(keys[:-1]) <= SOURCES

    def test_split_series_sum_equals_points_total(self, analytics_ready):
        base = {"granularity": "year", "date_from": DEFAULT_FROM, "date_to": DEFAULT_TO}
        points = _get(f"{API}/api/analytics/timeseries", params=base).json()
        split = _get(
            f"{API}/api/analytics/timeseries", params={**base, "split_by": "source", "top": 10}
        ).json()
        total_points = sum(p["contract_count"] for p in points["points"])
        total_series = sum(p["contract_count"] for s in split["series"] for p in s["points"])
        assert total_series == total_points


class TestTop:
    @pytest.mark.parametrize("dimension", ["procurer", "supplier", "cpv_division"])
    @pytest.mark.parametrize("metric", ["total_value", "contract_count"])
    def test_shape_and_share_sum(self, analytics_ready, dimension, metric):
        resp = _get(
            f"{API}/api/analytics/top",
            params={"dimension": dimension, "metric": metric, "n": 5},
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["dimension"] == dimension and d["metric"] == metric
        assert set(d["total"]) == {"total_value", "contract_count"}
        assert len(d["items"]) <= 5
        for item in d["items"]:
            assert set(item) >= {
                "key",
                "label",
                "ico",
                "total_value",
                "contract_count",
                "share_pct",
            }
            if dimension == "cpv_division":
                assert item["ico"] is None
                assert re.match(r"^\d{2}$", item["key"]) or re.match(r"^\d{8}$", item["key"])
        values = [i[metric] for i in d["items"]]
        assert values == sorted(values, reverse=True)
        if d["total"][metric]:
            share_sum = sum(i["share_pct"] for i in d["items"]) + d["other"]["share_pct"]
            assert share_sum == pytest.approx(100, abs=0.5)

    def test_drill_down_procurer_has_notices(self, analytics_ready):
        """A top procurer's ICO must lead to a non-empty /api/contracts list."""
        top = _get(f"{API}/api/analytics/top", params={"dimension": "procurer", "n": 1}).json()
        assert top["items"], "no procurers in the window"
        ico = top["items"][0]["ico"]
        listing = _get(
            f"{API}/api/contracts",
            params={
                "procurer_ico": ico,
                "date_from": DEFAULT_FROM,
                "date_to": DEFAULT_TO,
                "limit": 5,
            },
        ).json()
        assert listing["pagination"]["total"] > 0
        assert len(listing["data"]) > 0

    def test_cpv_division_drill_down_has_notices(self, analytics_ready):
        """A CPV division counted on the CPV page must yield a non-empty /zakazky list."""
        window = {"date_from": DEFAULT_FROM, "date_to": DEFAULT_TO}
        cpv = _get(f"{API}/api/analytics/cpv", params={"level": "division", **window}).json()
        top = next(i for i in cpv["items"] if i["contract_count"] > 0)
        listing = _get(
            f"{API}/api/contracts", params={**window, "cpv": top["prefix"], "limit": 1}
        ).json()
        assert listing["pagination"]["total"] > 0, (top["prefix"], top["contract_count"])


class TestConcentration:
    @pytest.mark.parametrize("dimension", ["supplier", "procurer"])
    def test_invariants(self, analytics_ready, dimension):
        d = _get(f"{API}/api/analytics/concentration", params={"dimension": dimension}).json()
        assert d["dimension"] == dimension
        assert 0 <= d["hhi"] <= 10_000
        assert d["hhi_band"] in {"low", "moderate", "high"}
        assert d["cr4_pct"] <= d["cr10_pct"] <= 100 + 1e-6
        assert len(d["top"]) <= 10
        cumulative = [t["cumulative_pct"] for t in d["top"]]
        assert cumulative == sorted(cumulative)
        if d["top"]:
            assert cumulative[-1] <= 100 + 1e-6
        if d["entity_count"] == 0:
            assert d["hhi"] == 0 and d["hhi_band"] == "low"


class TestCpv:
    def test_division_breakdown(self, analytics_ready):
        d = _get(f"{API}/api/analytics/cpv", params={"level": "division"}).json()
        assert d["level"] == "division"
        assert len(d["items"]) <= 45
        assert {
            "cpv_code",
            "prefix",
            "label_sk",
            "total_value",
            "contract_count",
            "share_pct",
        } <= set(d["items"][0])
        values = [i["total_value"] for i in d["items"]]
        assert values == sorted(values, reverse=True)
        if d["total_value"]:
            assert sum(i["share_pct"] for i in d["items"]) == pytest.approx(100, abs=0.5)


class TestCoverage:
    def test_all_five_sources_and_monthly_shape(self, analytics_ready):
        d = _get(f"{API}/api/analytics/coverage").json()
        assert {s["source"] for s in d["sources"]} == SOURCES
        assert len(d["sources"]) == 5
        for s in d["sources"]:
            assert set(s) >= {
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
            for key in (
                "with_value_pct",
                "with_cpv_pct",
                "with_supplier_ico_pct",
                "with_procurer_ico_pct",
            ):
                assert 0 <= s["quality"][key] <= 100
            assert s["contract_awards"] <= s["notices_total"]
        assert len(d["monthly"]) == 24
        assert all(re.match(r"^\d{4}-\d{2}$", m["period"]) for m in d["monthly"])
        assert set(d["canonical"]) == {"notices_with_canonical_id", "match_groups"}

    def test_coverage_ignores_common_filters(self, analytics_ready):
        plain = _get(f"{API}/api/analytics/coverage").json()
        filtered = _get(
            f"{API}/api/analytics/coverage", params={"source": "vestnik", "cpv": "45"}
        ).json()
        assert [s["notices_total"] for s in plain["sources"]] == [
            s["notices_total"] for s in filtered["sources"]
        ]


# --------------------------------------------------------------------------- consistency


class TestConsistency:
    @pytest.mark.parametrize("source", ["vestnik", "ted", "itms", "uvo"])
    def test_summary_matches_contracts_for_single_source(self, analytics_ready, source):
        """Per-source totals agree across the summary and the contracts list (same window)."""
        params = {"date_from": DEFAULT_FROM, "date_to": DEFAULT_TO, "source": source}
        summary = _get(f"{API}/api/analytics/summary", params=params).json()
        listing = _get(f"{API}/api/contracts", params={**params, "limit": 1}).json()
        assert summary["current"]["contract_count"] == listing["pagination"]["total"]

    def test_summary_matches_contracts_default_window(self, analytics_ready, default_summary):
        listing = _get(
            f"{API}/api/contracts",
            params={"date_from": DEFAULT_FROM, "date_to": DEFAULT_TO, "limit": 1},
        ).json()
        assert default_summary["current"]["contract_count"] == listing["pagination"]["total"]


# --------------------------------------------------------------------------- validation (422)


class TestValidation:
    @pytest.mark.parametrize(
        ("path", "params", "loc_field"),
        [
            ("summary", {"date_from": "2024-05-01", "date_to": "2023-01-01"}, "date_to"),
            ("summary", {"date_from": "2000-01-01", "date_to": "2020-01-01"}, "date_from"),
            ("summary", {"date_from": "2023-02-30"}, "date_from"),
            ("summary", {"date_from": "garbage"}, "date_from"),
            ("summary", {"cpv": "1"}, "cpv"),
            ("summary", {"cpv": "45-2"}, "cpv"),
            ("summary", {"source": "foo"}, "source"),
            ("summary", {"procurer_ico": "abc"}, "procurer_ico"),
            ("summary", {"supplier_ico": "1234567890123"}, "supplier_ico"),
            ("timeseries", {"granularity": "week"}, "granularity"),
            ("timeseries", {"split_by": "procurer"}, "split_by"),
            ("timeseries", {"top": 11}, "top"),
            ("timeseries", {"top": 0}, "top"),
            ("top", {}, "dimension"),
            ("top", {"dimension": "cpv"}, "dimension"),
            ("top", {"dimension": "procurer", "n": 0}, "n"),
            ("top", {"dimension": "procurer", "n": 51}, "n"),
            ("top", {"dimension": "procurer", "metric": "avg"}, "metric"),
            ("concentration", {"dimension": "cpv"}, "dimension"),
            ("cpv", {"level": "section"}, "level"),
        ],
    )
    def test_invalid_filters_are_422(self, analytics_ready, path, params, loc_field):
        resp = _get(f"{API}/api/analytics/{path}", params=params)
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert isinstance(body["detail"], list)
        assert any(loc_field in err["loc"] for err in body["detail"]), body

    def test_422_body_does_not_leak_traceback(self, analytics_ready):
        resp = _get(f"{API}/api/analytics/summary", params={"source": "x" * 500})
        assert resp.status_code == 422
        assert "Traceback" not in resp.text and 'File "' not in resp.text


# --------------------------------------------------------------------------- metrics


def _scrape(url: str) -> str:
    resp = _get(url)
    assert resp.status_code == 200, resp.text
    return resp.text


class TestMetrics:
    def test_api_exposes_spec_families(self, analytics_ready):
        # Make sure the route-template label exists for an analytics route.
        _get(f"{API}/api/analytics/cpv")
        text = _scrape(f"{API}/metrics")
        for family in API_FAMILIES:
            assert family in text, f"missing {family}"
        assert 'route="/api/analytics/cpv"' in text
        assert not re.search(r'route="/api/analytics/cpv\?', text), (
            "raw path leaked into route label"
        )

    def test_mcp_exposes_spec_families(self, compose_stack):
        text = _scrape(f"{MCP}/metrics")
        for family in MCP_FAMILIES:
            assert f"# TYPE {family} " in text, f"missing {family}"

    def test_worker_exposes_spec_families(self, compose_stack):
        """Scrape the running ingestor from inside the compose network (no host port)."""
        script = (
            "import urllib.request,sys;"
            "sys.stdout.write(urllib.request.urlopen('http://ingestor:8095/metrics',timeout=10).read().decode())"
        )
        result = _compose("exec", "-T", "api", "python", "-c", script)
        assert result.returncode == 0, result.stderr
        for family in WORKER_FAMILIES:
            assert family in result.stdout, f"missing {family}"


# --------------------------------------------------------------------------- GUI


class TestGui:
    @pytest.mark.parametrize("page", ANALYTICS_PAGES)
    def test_analytics_page_serves_spa_shell(self, compose_stack, page):
        resp = _get(f"{GUI}/analytika/{page}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert '<div id="root">' in resp.text
        assert 'lang="sk"' in resp.text

    def test_legacy_root_redirects_are_served_by_spa(self, compose_stack):
        resp = _get(f"{GUI}/analytika", follow_redirects=True)
        assert resp.status_code == 200
        assert '<div id="root">' in resp.text
