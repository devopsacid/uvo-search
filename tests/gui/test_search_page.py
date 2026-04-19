"""Tests for the search page (ui.table + search_box rework)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from nicegui import ui
from nicegui.testing import User

MOCK_RESULTS = {
    "items": [
        {
            "_id": "1",
            "title": "Stavebné práce",
            "procurer": {"name": "MV SR"},
            "final_value": 120000,
            "publication_date": "2024-01-15",
        }
    ],
    "total": 1,
}


@pytest.mark.asyncio
async def test_search_page_lists_all_on_open(user: User) -> None:
    with patch.dict(os.environ, {"STORAGE_SECRET": "x", "UVOSTAT_API_TOKEN": "dummy"}):
        with patch(
            "uvo_gui.mcp_client.call_tool",
            new_callable=AsyncMock,
            return_value=MOCK_RESULTS,
        ):
            import uvo_gui.pages.search  # noqa: F401

            await user.open("/")
            # Table should be rendered and have the mocked row
            table = user.find(kind=ui.table).elements.pop()
            assert any(r.get("title") == "Stavebné práce" for r in table.rows)
            # Detail panel placeholder is still shown (no row clicked yet)
            await user.should_see("Vyberte zákazku zo zoznamu")


@pytest.mark.asyncio
async def test_search_page_shows_error_on_failure(
    user: User, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    with patch.dict(os.environ, {"STORAGE_SECRET": "x", "UVOSTAT_API_TOKEN": "dummy"}):
        with patch(
            "uvo_gui.mcp_client.call_tool",
            new_callable=AsyncMock,
            side_effect=RuntimeError("backend down"),
        ):
            import uvo_gui.pages.search  # noqa: F401

            with caplog.at_level(logging.ERROR, logger="uvo_gui.pages.search"):
                await user.open("/")
            await user.should_see("Chyba pri vyhľadávaní")
    # Clear captured error records so the fixture teardown check doesn't fail
    caplog.records.clear()
