"""Tests for the split-panel search page."""
from unittest.mock import AsyncMock, patch

import pytest
from nicegui.testing import User


MOCK_RESULTS = {
    "items": [
        {
            "id": "1",
            "nazov": "Stavebné práce",
            "obstaravatel_nazov": "MV SR",
            "konecna_hodnota": 120000,
            "datum_zverejnenia": "2024-01-15",
            "cpv_kod": "45100000-8",
            "stav": "Zadaná zákazka",
            "dodavatelia": [{"nazov": "ACME s.r.o.", "ico": "12345678"}],
        }
    ],
    "total": 1,
}


@pytest.mark.asyncio
async def test_search_page_shows_search_form(user: User) -> None:
    import uvo_gui.pages.search  # noqa: F401
    await user.open("/")
    await user.should_see("Hľadať zákazku")
    await user.should_see("Hľadať")


@pytest.mark.asyncio
async def test_search_page_shows_empty_state(user: User) -> None:
    import uvo_gui.pages.search  # noqa: F401
    await user.open("/")
    await user.should_see("Vyberte zákazku zo zoznamu")


@pytest.mark.asyncio
async def test_search_page_shows_results_after_search(user: User) -> None:
    import uvo_gui.pages.search  # noqa: F401
    with patch(
        "uvo_gui.mcp_client.call_tool",
        new_callable=AsyncMock,
        return_value=MOCK_RESULTS,
    ):
        await user.open("/")
        await user.should_see("Hľadať")
        user.find("Hľadať").click()
        await user.should_see("Stavebné práce")


@pytest.mark.asyncio
async def test_search_page_shows_detail_on_click(user: User) -> None:
    import uvo_gui.pages.search  # noqa: F401
    with patch(
        "uvo_gui.mcp_client.call_tool",
        new_callable=AsyncMock,
        return_value=MOCK_RESULTS,
    ):
        await user.open("/")
        user.find("Hľadať").click()
        await user.should_see("Stavebné práce")
        user.find("Stavebné práce").click()
        await user.should_see("MV SR")
        await user.should_see("ACME s.r.o.")
