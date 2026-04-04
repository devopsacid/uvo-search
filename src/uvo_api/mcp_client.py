"""MCP client wrapper for calling MCP server tools from the analytics API."""

import json
import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from uvo_api.config import ApiSettings

logger = logging.getLogger(__name__)

_settings_cache = None


def _get_settings() -> ApiSettings:
    """Lazily load and cache API settings."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = ApiSettings()
    return _settings_cache


async def call_tool(tool_name: str, arguments: dict) -> dict:
    """Call a tool on the MCP server and return the parsed JSON response."""
    settings = _get_settings()
    async with streamablehttp_client(settings.mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            for content in result.content:
                if hasattr(content, "text"):
                    return json.loads(content.text)
            raise ValueError(f"No text content in response from {tool_name}")
