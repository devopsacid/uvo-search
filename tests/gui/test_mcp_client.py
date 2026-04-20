"""Tests for the MCP client wrapper used by the NiceGUI frontend."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCallTool:
    @pytest.fixture(autouse=True)
    def _set_env(self):
        env = {"STORAGE_SECRET": "test-secret"}
        with patch.dict(os.environ, env, clear=False):
            yield

    async def test_call_tool_returns_parsed_json(self):
        """call_tool returns a parsed dict from the first text content item."""
        payload = {"items": [{"id": 1, "nazov": "Test"}], "total": 1}

        mock_content = MagicMock()
        mock_content.text = json.dumps(payload)

        mock_result = MagicMock()
        mock_result.content = [mock_content]

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        mock_read = MagicMock()
        mock_write = MagicMock()

        # streamablehttp_client is an async context manager returning (read, write, _)
        mock_http_cm = MagicMock()
        mock_http_cm.__aenter__ = AsyncMock(return_value=(mock_read, mock_write, None))
        mock_http_cm.__aexit__ = AsyncMock(return_value=False)

        # ClientSession is an async context manager returning the session
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("uvo_gui.mcp_client.streamablehttp_client", return_value=mock_http_cm),
            patch("uvo_gui.mcp_client.ClientSession", return_value=mock_session_cm),
        ):
            from uvo_gui.mcp_client import call_tool

            result = await call_tool("search_completed_procurements", {"q": "test"})

        assert result == payload
        mock_session.call_tool.assert_called_once_with(
            "search_completed_procurements", {"q": "test"}
        )

    async def test_call_tool_raises_on_no_text_content(self):
        """call_tool raises ValueError when response contains no text content."""
        mock_content = MagicMock(spec=[])  # no 'text' attribute

        mock_result = MagicMock()
        mock_result.content = [mock_content]

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        mock_read = MagicMock()
        mock_write = MagicMock()

        mock_http_cm = MagicMock()
        mock_http_cm.__aenter__ = AsyncMock(return_value=(mock_read, mock_write, None))
        mock_http_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("uvo_gui.mcp_client.streamablehttp_client", return_value=mock_http_cm),
            patch("uvo_gui.mcp_client.ClientSession", return_value=mock_session_cm),
        ):
            from uvo_gui.mcp_client import call_tool

            with pytest.raises(ValueError, match="No text content"):
                await call_tool("get_procurement_detail", {"id": "123"})
