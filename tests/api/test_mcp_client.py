import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_call_tool_returns_parsed_json():
    mock_result = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps({"data": [{"id": "1"}], "total": 1})
    mock_result.content = [mock_content]

    mock_session = AsyncMock()
    mock_session.call_tool.return_value = mock_result
    mock_session.initialize = AsyncMock()

    with patch("uvo_api.mcp_client.streamablehttp_client") as mock_transport, \
         patch("uvo_api.mcp_client.ClientSession") as mock_session_cls, \
         patch("uvo_api.mcp_client._get_settings") as mock_get_settings:

        mock_transport.return_value.__aenter__ = AsyncMock(return_value=(None, None, None))
        mock_transport.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.mcp_server_url = "http://localhost:8000/mcp"
        mock_get_settings.return_value = mock_settings

        from uvo_api.mcp_client import call_tool
        result = await call_tool("search_completed_procurements", {})

    assert result == {"data": [{"id": "1"}], "total": 1}


@pytest.mark.asyncio
async def test_call_tool_raises_on_no_text_content():
    mock_result = MagicMock()
    mock_result.content = []

    mock_session = AsyncMock()
    mock_session.call_tool.return_value = mock_result
    mock_session.initialize = AsyncMock()

    with patch("uvo_api.mcp_client.streamablehttp_client") as mock_transport, \
         patch("uvo_api.mcp_client.ClientSession") as mock_session_cls, \
         patch("uvo_api.mcp_client._get_settings") as mock_get_settings:

        mock_transport.return_value.__aenter__ = AsyncMock(return_value=(None, None, None))
        mock_transport.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.mcp_server_url = "http://localhost:8000/mcp"
        mock_get_settings.return_value = mock_settings

        from uvo_api.mcp_client import call_tool
        with pytest.raises(ValueError, match="No text content"):
            await call_tool("search_completed_procurements", {})
