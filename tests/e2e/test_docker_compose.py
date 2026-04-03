"""End-to-end tests that run against docker-compose services.

These tests build and start the full stack (MCP server + NiceGUI GUI) via
docker compose, then verify both services are healthy and the GUI can
communicate with the MCP server.

Usage:
    pytest tests/e2e/ -m e2e -v

Requires:
    - Docker and docker compose installed
    - No services already running on ports 8000/8080
"""

import subprocess
import time

import httpx
import pytest

COMPOSE_FILE = "docker-compose.yml"
MCP_URL = "http://localhost:8000"
GUI_URL = "http://localhost:8080"

# Max time to wait for services to be healthy (seconds)
STARTUP_TIMEOUT = 120
POLL_INTERVAL = 3


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

    # Wait for MCP server health check
    mcp_healthy = _wait_for_health(f"{MCP_URL}/health", STARTUP_TIMEOUT)
    if not mcp_healthy:
        _dump_logs()
        subprocess.run(["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"], timeout=30)
        pytest.fail("MCP server did not become healthy within timeout")

    # Wait for GUI health check
    gui_healthy = _wait_for_health(GUI_URL, STARTUP_TIMEOUT)
    if not gui_healthy:
        _dump_logs()
        subprocess.run(["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"], timeout=30)
        pytest.fail("GUI did not become healthy within timeout")

    yield

    # Teardown
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"],
        capture_output=True,
        timeout=30,
    )


def _wait_for_health(url: str, timeout: int) -> bool:
    """Poll a URL until it returns 200 or timeout."""
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


@pytest.mark.e2e
class TestMCPServerHealth:
    """Verify MCP server is running and responsive."""

    def test_health_endpoint(self, docker_compose_up):
        resp = httpx.get(f"{MCP_URL}/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "uvo-mcp"

    def test_mcp_endpoint_exists(self, docker_compose_up):
        """The /mcp endpoint should accept POST (MCP protocol)."""
        resp = httpx.post(
            f"{MCP_URL}/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        # MCP endpoint should respond (even if protocol error, it should not 404)
        assert resp.status_code != 404


@pytest.mark.e2e
class TestGUIHealth:
    """Verify NiceGUI frontend is running and serves pages."""

    def test_root_page_loads(self, docker_compose_up):
        resp = httpx.get(GUI_URL, timeout=10, follow_redirects=True)
        assert resp.status_code == 200
        assert "UVO Search" in resp.text

    def test_gui_serves_html(self, docker_compose_up):
        resp = httpx.get(GUI_URL, timeout=10, follow_redirects=True)
        assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.e2e
class TestMCPToolsViaMCP:
    """Test MCP tools are callable through the streamable-http transport."""

    def test_list_tools_via_mcp_client(self, docker_compose_up):
        """Use the MCP client SDK to list available tools."""
        import asyncio

        async def _list_tools():
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            async with streamablehttp_client(f"{MCP_URL}/mcp") as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return [t.name for t in tools.tools]

        tool_names = asyncio.run(_list_tools())
        assert "search_completed_procurements" in tool_names
        assert "get_procurement_detail" in tool_names
        assert "find_procurer" in tool_names
        assert "find_supplier" in tool_names

    def test_call_search_tool(self, docker_compose_up):
        """Call search_completed_procurements — will likely return API error
        (no real token) but should not crash."""
        import asyncio
        import json

        async def _call_search():
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            async with streamablehttp_client(f"{MCP_URL}/mcp") as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "search_completed_procurements",
                        {"limit": 5, "offset": 0},
                    )
                    for content in result.content:
                        if hasattr(content, "text"):
                            return json.loads(content.text)
                    return None

        result = asyncio.run(_call_search())
        assert result is not None
        # With a fake token, we expect either real data or an error dict
        assert "data" in result or "error" in result
