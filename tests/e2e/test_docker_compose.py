"""End-to-end tests that run against docker-compose services.

These tests build and start the full stack (MCP server + React GUI) via
docker compose, then verify both services are healthy and the GUI can
communicate with the MCP server.

Usage:
    pytest tests/e2e/ -m e2e -v

Requires:
    - Docker and docker compose installed
    - No services already running on ports 8000/8080
"""

import httpx
import pytest

MCP_URL = "http://localhost:8000"
GUI_URL = "http://localhost:8080"


@pytest.mark.e2e
class TestMCPServerHealth:
    """Verify MCP server is running and responsive."""

    def test_health_endpoint(self, compose_stack):
        resp = httpx.get(f"{MCP_URL}/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "uvo-mcp"

    def test_mcp_endpoint_exists(self, compose_stack):
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
    """Verify React frontend is running and serves pages."""

    def test_root_page_loads(self, compose_stack):
        resp = httpx.get(GUI_URL, timeout=10, follow_redirects=True)
        assert resp.status_code == 200
        assert "UVO Search" in resp.text

    def test_gui_serves_html(self, compose_stack):
        resp = httpx.get(GUI_URL, timeout=10, follow_redirects=True)
        assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.e2e
class TestMCPToolsViaMCP:
    """Test MCP tools are callable through the streamable-http transport."""

    def test_list_tools_via_mcp_client(self, compose_stack):
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

    def test_call_search_tool(self, compose_stack):
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
