"""MCP client wrapper for calling MCP server tools from the analytics API."""

import json
import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from uvo_api.config import ApiSettings

logger = logging.getLogger(__name__)


def _get_settings() -> ApiSettings:
    """Return API settings, reading from environment each time for test isolation."""
    return ApiSettings()


class McpToolError(RuntimeError):
    """Raised when an MCP tool call returns an error or unparseable payload."""


async def call_tool(tool_name: str, arguments: dict) -> dict:
    """Call a tool on the MCP server and return the parsed JSON response."""
    settings = _get_settings()
    async with streamablehttp_client(settings.mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            text = next(
                (c.text for c in result.content if hasattr(c, "text")),
                None,
            )
            if text is None:
                raise McpToolError(f"No text content in response from {tool_name}")
            if result.isError:
                raise McpToolError(f"{tool_name} failed: {text}")
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                raise McpToolError(
                    f"{tool_name} returned non-JSON payload: {text[:200]}"
                ) from e
