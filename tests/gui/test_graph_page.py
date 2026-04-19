import os
from unittest.mock import AsyncMock, patch

from nicegui.testing import User


async def test_graph_page_shows_labels(user: User):
    mock = AsyncMock(return_value={"nodes": [], "edges": []})
    with patch.dict(os.environ, {"STORAGE_SECRET": "test", "UVOSTAT_API_TOKEN": "dummy"}):
        with patch("uvo_gui.mcp_client.call_tool", mock):
            import uvo_gui.pages.graph  # noqa: F401  # ensure route registered

            await user.open("/graph")
            await user.should_see("Sieť vzťahov")
            await user.should_see("Ego-sieť")
            await user.should_see("CPV-sieť")
