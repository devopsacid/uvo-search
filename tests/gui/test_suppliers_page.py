"""Tests for the Dodavatelia page."""
from unittest.mock import AsyncMock, patch

import pytest
from nicegui.testing import User

MOCK_SUPPLIERS = {
    "items": [
        {"id": "s1", "nazov": "ACME Stavby s.r.o.", "ico": "12345678", "zakazky_count": 24, "total_value": 2100000},
        {"id": "s2", "nazov": "IT Solutions a.s.", "ico": "87654321", "zakazky_count": 41, "total_value": 5600000},
    ],
    "total": 2,
}


@pytest.mark.asyncio
async def test_suppliers_page_shows_search_form(user: User) -> None:
    import uvo_gui.pages.suppliers  # noqa: F401
    await user.open("/suppliers")
    await user.should_see("Hľadať dodávateľa")
    await user.should_see("Hľadať")


@pytest.mark.asyncio
async def test_suppliers_page_shows_results(user: User) -> None:
    import uvo_gui.pages.suppliers  # noqa: F401
    with patch(
        "uvo_gui.mcp_client.call_tool",
        new_callable=AsyncMock,
        return_value=MOCK_SUPPLIERS,
    ):
        await user.open("/suppliers")
        user.find("Hľadať").click()
        await user.should_see("ACME Stavby s.r.o.")
        await user.should_see("IČO: 12345678")
