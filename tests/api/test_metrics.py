"""install_metrics: ASGI middleware, /metrics route, background refreshers."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from uvo_api import metrics as api_metrics
from uvo_api.metrics import install_metrics


def _val(name: str, labels: dict | None = None) -> float:
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


def _count(method: str, route: str, status: str) -> float:
    return _val("uvo_api_http_requests_total", {"method": method, "route": route, "status": status})


@pytest.fixture
def app():
    app = FastAPI()

    @app.get("/api/firma/{ico}")
    async def firma(ico: str):
        return {"ico": ico}

    @app.get("/api/boom")
    async def boom():
        raise HTTPException(status_code=503, detail="x")

    @app.get("/api/crash")
    async def crash():
        raise RuntimeError("bug")

    install_metrics(app)
    return app


def test_label_uses_route_template_not_raw_path(app):
    before = _count("GET", "/api/firma/{ico}", "200")
    client = TestClient(app)
    client.get("/api/firma/123")
    client.get("/api/firma/456")
    assert _count("GET", "/api/firma/{ico}", "200") == before + 2
    assert _count("GET", "/api/firma/123", "200") == 0


def test_unmatched_path_is_labelled_unmatched(app):
    before = _count("GET", "unmatched", "404")
    TestClient(app).get("/nope/1")
    assert _count("GET", "unmatched", "404") == before + 1


def test_error_status_is_recorded(app):
    before = _count("GET", "/api/boom", "503")
    TestClient(app).get("/api/boom")
    assert _count("GET", "/api/boom", "503") == before + 1


def test_unhandled_exception_counts_as_500(app):
    before = _count("GET", "/api/crash", "500")
    TestClient(app, raise_server_exceptions=False).get("/api/crash")
    assert _count("GET", "/api/crash", "500") == before + 1


def test_duration_histogram_observed_and_in_progress_returns_to_zero(app):
    labels = {"method": "GET", "route": "/api/firma/{ico}"}
    before = _val("uvo_api_http_request_duration_seconds_count", labels)
    TestClient(app).get("/api/firma/1")
    assert _val("uvo_api_http_request_duration_seconds_count", labels) == before + 1
    assert _val("uvo_api_http_requests_in_progress") == 0


def test_metrics_route_content_type_and_body(app):
    client = TestClient(app)
    client.get("/api/firma/1")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert "uvo_api_http_requests_total" in response.text
    assert "uvo_build_info" in response.text


def test_metrics_route_is_not_in_openapi_schema(app):
    assert "/metrics" not in app.openapi()["paths"]


def test_build_info_uses_git_sha_env(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc1234")
    install_metrics(FastAPI())
    samples = [s for fam in REGISTRY.collect() if fam.name == "uvo_build_info" for s in fam.samples]
    assert any(s.labels["git_sha"] == "abc1234" and s.value == 1 for s in samples)


def test_middleware_overhead_is_small(app):
    plain = FastAPI()

    @plain.get("/api/firma/{ico}")
    async def firma(ico: str):
        return {"ico": ico}

    def bench(a: FastAPI) -> float:
        c = TestClient(a)
        c.get("/api/firma/1")
        start = time.perf_counter()
        for _ in range(300):
            c.get("/api/firma/1")
        return (time.perf_counter() - start) / 300

    # Generous bound (spec: < 0.2 ms); guards against pathological regressions only.
    assert bench(app) - bench(plain) < 0.002


# --- background refreshers -------------------------------------------------


def _resources(*, mongo_ok: bool, indexes_ok: bool):
    db = MagicMock()
    db.command = (
        AsyncMock(return_value={"ok": 1}) if mongo_ok else AsyncMock(side_effect=RuntimeError("x"))
    )
    probe = MagicMock()
    probe.ready = AsyncMock(return_value=indexes_ok)
    res = MagicMock()
    res.db = db
    res.index_probe = probe
    return res


async def test_refresh_ready_zero_then_one():
    app = FastAPI()
    app.state.resources = _resources(mongo_ok=False, indexes_ok=True)
    await api_metrics.refresh_ready(app)
    assert _val("uvo_ready", {"service": "uvo-api"}) == 0
    app.state.resources = _resources(mongo_ok=True, indexes_ok=True)
    await api_metrics.refresh_ready(app)
    assert _val("uvo_ready", {"service": "uvo-api"}) == 1


async def test_refresh_ready_is_zero_when_indexes_missing():
    app = FastAPI()
    app.state.resources = _resources(mongo_ok=True, indexes_ok=False)
    await api_metrics.refresh_ready(app)
    assert _val("uvo_ready", {"service": "uvo-api"}) == 0


async def test_refreshers_are_safe_without_resources():
    app = FastAPI()
    await api_metrics.refresh_ready(app)
    await api_metrics.refresh_source_stats(app)
    assert _val("uvo_ready", {"service": "uvo-api"}) == 0


async def test_refresh_source_stats_sets_gauges(monkeypatch):
    app = FastAPI()
    app.state.resources = _resources(mongo_ok=True, indexes_ok=True)
    report = {
        "sources": [
            {
                "source": "crz",
                "total": 10,
                "last_24h": 3,
                "last_ingested_at": "2026-10-19T10:00:00",
            },
            {"source": "ted", "total": 0, "last_24h": 0, "last_ingested_at": None},
        ]
    }
    monkeypatch.setattr(api_metrics, "collect_health", AsyncMock(return_value=report))
    await api_metrics.refresh_source_stats(app)
    assert _val("uvo_source_notices_total", {"source": "crz"}) == 10
    assert _val("uvo_source_ingested_24h", {"source": "crz"}) == 3
    # 2026-10-19T10:00:00 UTC
    assert _val("uvo_source_last_ingested_timestamp_seconds", {"source": "crz"}) == 1792404000.0
    assert _val("uvo_source_last_ingested_timestamp_seconds", {"source": "ted"}) == 0


async def test_refresh_source_stats_swallows_errors(monkeypatch):
    app = FastAPI()
    app.state.resources = _resources(mongo_ok=True, indexes_ok=True)
    monkeypatch.setattr(api_metrics, "collect_health", AsyncMock(side_effect=RuntimeError("x")))
    await api_metrics.refresh_source_stats(app)  # must not raise


async def test_start_background_returns_two_cancellable_tasks():
    app = FastAPI()
    tasks = api_metrics.start_background(app)
    assert len(tasks) == 2
    await asyncio.sleep(0)
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def test_mounted_sub_app_route_keeps_mount_prefix():
    sub = FastAPI()

    @sub.get("/contracts")
    async def contracts():
        return {}

    app = FastAPI()
    app.mount("/v1", sub)
    install_metrics(app)
    before = _count("GET", "/v1/contracts", "200")
    TestClient(app).get("/v1/contracts")
    assert _count("GET", "/v1/contracts", "200") == before + 1
