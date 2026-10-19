"""E2E checks for the local monitoring profile (spec section 8.5).

Skipped unless ``MONITORING_PROFILE=1``; start the profile first:

    docker compose --profile monitoring up -d prometheus grafana

Prometheus is published on 127.0.0.1:9090 and Grafana on 127.0.0.1:3000.
Grafana admin credentials come from ``GRAFANA_ADMIN_PASSWORD`` (compose default
``uvo_grafana_dev``); the password is never printed.
"""

import os

import httpx
import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("MONITORING_PROFILE") != "1",
        reason="monitoring profile not requested (set MONITORING_PROFILE=1)",
    ),
]

PROMETHEUS = "http://localhost:9090"
GRAFANA = "http://localhost:3000"
EXPECTED_DASHBOARDS = {
    "uvo-pipeline-health",
    "uvo-api-performance",
    "uvo-data-freshness",
}
# Targets that must be up for the profile to be useful; the four extractors are
# intentionally not required because they are stopped in some local runs.
REQUIRED_JOBS = {"uvo-api", "uvo-mcp"}
REQUIRED_WORKER_COMPONENTS = {"ingestor", "dedup-worker"}


def _targets() -> list[dict]:
    resp = httpx.get(f"{PROMETHEUS}/api/v1/targets", timeout=15)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    return body["data"]["activeTargets"]


class TestPrometheus:
    def test_api_and_mcp_targets_up(self):
        targets = _targets()
        for job in REQUIRED_JOBS:
            matching = [t for t in targets if t["labels"].get("job") == job]
            assert matching, f"no target for job {job}"
            down = [t["scrapeUrl"] for t in matching if t["health"] != "up"]
            assert not down, f"{job} targets not up: {down}"

    def test_running_workers_targets_up(self):
        targets = _targets()
        by_component = {
            t["labels"].get("component"): t
            for t in targets
            if t["labels"].get("job") == "uvo-workers"
        }
        for component in REQUIRED_WORKER_COMPONENTS:
            assert component in by_component, f"no uvo-workers target for {component}"
            target = by_component[component]
            assert target["health"] == "up", f"{component}: {target.get('lastError')}"

    def test_all_worker_targets_report_state(self):
        """Every worker target is scraped (up or down), i.e. it is in the config."""
        components = {
            t["labels"].get("component")
            for t in _targets()
            if t["labels"].get("job") == "uvo-workers"
        }
        assert components >= {
            "extractor-vestnik",
            "extractor-crz",
            "extractor-ted",
            "extractor-itms",
            "ingestor",
            "dedup-worker",
        }

    def test_rule_file_loaded(self):
        resp = httpx.get(f"{PROMETHEUS}/api/v1/rules", timeout=15)
        assert resp.status_code == 200
        groups = resp.json()["data"]["groups"]
        names = {r["name"] for g in groups for r in g["rules"]}
        assert any(n.startswith("Uvo") for n in names), names


class TestGrafana:
    @pytest.fixture(scope="class")
    def auth(self):
        return ("admin", os.environ.get("GRAFANA_ADMIN_PASSWORD", "uvo_grafana_dev"))

    def test_search_returns_three_uvo_dashboards(self, auth):
        resp = httpx.get(
            f"{GRAFANA}/api/search",
            params={"type": "dash-db", "query": "UVO"},
            auth=auth,
            timeout=15,
        )
        assert resp.status_code == 200, resp.status_code
        uids = {d["uid"] for d in resp.json()}
        assert EXPECTED_DASHBOARDS <= uids, uids
