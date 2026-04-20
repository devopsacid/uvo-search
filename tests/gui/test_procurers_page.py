"""Tests for the Obstaravatelia page (ui.table + search_box rework)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from nicegui import ui
from nicegui.testing import User

MOCK_PROCURERS = {
    "items": [
        {
            "name": "Ministerstvo vnútra SR",
            "ico": "00151866",
            "contract_count": 342,
            "total_value": 12400000,
        },
        {
            "name": "MDVaRR SR",
            "ico": "30416094",
            "contract_count": 187,
            "total_value": 8100000,
        },
    ],
    "total": 2,
}


@pytest.mark.asyncio
async def test_procurers_page_lists_on_open(user: User) -> None:
    with patch.dict(os.environ, {"STORAGE_SECRET": "x"}):
        with patch(
            "uvo_gui.mcp_client.call_tool",
            new_callable=AsyncMock,
            return_value=MOCK_PROCURERS,
        ):
            import uvo_gui.pages.procurers  # noqa: F401

            await user.open("/procurers")
            await user.should_see("Obstaravatelia")
            table = user.find(kind=ui.table).elements.pop()
            names = [r.get("name") for r in table.rows]
            assert "Ministerstvo vnútra SR" in names
            assert "MDVaRR SR" in names
