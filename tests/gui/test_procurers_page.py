"""Tests for the Obstaravatelia page."""
from unittest.mock import AsyncMock, patch

import pytest
from nicegui.testing import User

MOCK_PROCURERS = {
    "items": [
        {"id": "p1", "nazov": "Ministerstvo vnútra SR", "ico": "00151866", "zakazky_count": 342, "total_value": 12400000},
        {"id": "p2", "nazov": "MDVaRR SR", "ico": "30416094", "zakazky_count": 187, "total_value": 8100000},
    ],
    "total": 2,
}


@pytest.mark.asyncio
async def test_procurers_page_shows_search_form(user: User) -> None:
    import uvo_gui.pages.procurers  # noqa: F401
    await user.open("/procurers")
    await user.should_see("Hľadať obstarávateľa")
    await user.should_see("Hľadať")


@pytest.mark.asyncio
async def test_procurers_page_shows_results(user: User) -> None:
    import uvo_gui.pages.procurers  # noqa: F401
    with patch(
        "uvo_gui.mcp_client.call_tool",
        new_callable=AsyncMock,
        return_value=MOCK_PROCURERS,
    ):
        await user.open("/procurers")
        user.find("Hľadať").click()
        await user.should_see("Ministerstvo vnútra SR")
        await user.should_see("MDVaRR SR")
