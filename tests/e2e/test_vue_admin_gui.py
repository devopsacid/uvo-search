"""End-to-end tests for the Vue admin GUI service and FastAPI analytics API.

Tests build and start the full docker-compose stack, then verify:
- Analytics API (port 8001) health, endpoints, and search params
- Admin GUI (port 3000) SPA serving and nginx proxy behaviour

Usage:
    pytest tests/e2e/test_vue_admin_gui.py -m e2e -v

Requires:
    - Docker and docker compose installed
    - No services already running on ports 8000/8001/3000/8080
"""

import subprocess
import time

import httpx
import pytest

COMPOSE_FILE = "docker-compose.yml"
API_URL = "http://localhost:8001"
ADMIN_GUI_URL = "http://localhost:3000"

STARTUP_TIMEOUT = 120
POLL_INTERVAL = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_health(url: str, timeout: int) -> bool:
    """Poll a URL until it returns 200 or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=5)
            if resp.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
            pass
        time.sleep(POLL_INTERVAL)
    return False


def _dump_logs():
    """Print docker compose logs for debugging failed startups."""
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "logs", "--tail=50"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    print("=== Docker Compose Logs ===")
    print(result.stdout)
    if result.stderr:
        print(result.stderr)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def docker_compose_up():
    """Build and start docker-compose services, tear down after tests."""
    # Build images
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "build"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(f"docker compose build failed:\n{result.stderr}")

    # Start services in detached mode
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(f"docker compose up failed:\n{result.stderr}")

    # Wait for analytics API health
    api_healthy = _wait_for_health(f"{API_URL}/health", STARTUP_TIMEOUT)
    if not api_healthy:
        _dump_logs()
        subprocess.run(["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"], timeout=30)
        pytest.fail("Analytics API did not become healthy within timeout")

    # Wait for admin GUI health
    gui_healthy = _wait_for_health(ADMIN_GUI_URL, STARTUP_TIMEOUT)
    if not gui_healthy:
        _dump_logs()
        subprocess.run(["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"], timeout=30)
        pytest.fail("Admin GUI did not become healthy within timeout")

    yield

    # Teardown
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"],
        capture_output=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestAnalyticsApiHealth:
    """Verify analytics API (port 8001) is running and responsive."""

    def test_health_endpoint(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "uvo-api"

    def test_cors_header_present(self, docker_compose_up):
        resp = httpx.get(
            f"{API_URL}/health",
            headers={"Origin": "http://localhost:3000"},
            timeout=10,
        )
        assert "access-control-allow-origin" in resp.headers


@pytest.mark.e2e
class TestAnalyticsApiEndpoints:
    """Verify analytics API list and dashboard endpoints return expected shapes."""

    def test_contracts_list(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/contracts", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "pagination" in data

    def test_suppliers_list(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/suppliers", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "pagination" in data

    def test_procurers_list(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/procurers", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "pagination" in data

    def test_dashboard_summary(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/dashboard/summary", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_value" in data
        assert "contract_count" in data
        assert "avg_value" in data
        assert "active_suppliers" in data

    def test_dashboard_spend_by_year(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/dashboard/spend-by-year", timeout=10)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_dashboard_by_cpv(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/dashboard/by-cpv", timeout=10)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_dashboard_recent(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/dashboard/recent", timeout=10)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_dashboard_top_suppliers(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/dashboard/top-suppliers", timeout=10)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_dashboard_top_procurers(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/dashboard/top-procurers", timeout=10)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


@pytest.mark.e2e
class TestAdminGuiService:
    """Verify the Vue admin GUI nginx container serves the SPA correctly."""

    def test_root_page_loads(self, docker_compose_up):
        resp = httpx.get(ADMIN_GUI_URL, timeout=10, follow_redirects=True)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_spa_index_html(self, docker_compose_up):
        resp = httpx.get(ADMIN_GUI_URL, timeout=10, follow_redirects=True)
        assert "<div id=\"app\">" in resp.text

    def test_spa_fallback_routing(self, docker_compose_up):
        """Nginx SPA fallback: deep routes should return the index, not 404."""
        resp = httpx.get(f"{ADMIN_GUI_URL}/suppliers/12345", timeout=10, follow_redirects=True)
        assert resp.status_code == 200

    def test_spa_fallback_contracts(self, docker_compose_up):
        resp = httpx.get(f"{ADMIN_GUI_URL}/contracts", timeout=10, follow_redirects=True)
        assert resp.status_code == 200

    def test_api_proxy_via_nginx(self, docker_compose_up):
        """Admin GUI nginx should proxy /api/* requests to the analytics API."""
        resp = httpx.get(f"{ADMIN_GUI_URL}/api/health", timeout=10, follow_redirects=True)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data


@pytest.mark.e2e
class TestAnalyticsApiSearchParams:
    """Verify analytics API respects pagination and search query parameters."""

    def test_contracts_pagination(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/contracts?limit=5&offset=0", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        pagination = data["pagination"]
        assert pagination["limit"] == 5
        assert pagination["offset"] == 0

    def test_contracts_search_param(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/contracts?q=test", timeout=10)
        assert resp.status_code == 200

    def test_suppliers_search_param(self, docker_compose_up):
        resp = httpx.get(f"{API_URL}/api/suppliers?q=test", timeout=10)
        assert resp.status_code == 200
