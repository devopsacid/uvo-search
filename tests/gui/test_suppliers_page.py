"""Tests for the Dodavatelia page (ui.table + search_box rework)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from nicegui import ui
from nicegui.testing import User

MOCK_SUPPLIERS = {
    "items": [
        {
            "name": "ACME Stavby s.r.o.",
            "ico": "12345678",
            "contract_count": 24,
            "total_value": 2100000,
        },
        {
            "name": "IT Solutions a.s.",
            "ico": "87654321",
            "contract_count": 41,
            "total_value": 5600000,
        },
    ],
    "total": 2,
}


@pytest.mark.asyncio
async def test_suppliers_page_lists_on_open(user: User) -> None:
    with patch.dict(os.environ, {"STORAGE_SECRET": "x", "UVOSTAT_API_TOKEN": "dummy"}):
        with patch(
            "uvo_gui.mcp_client.call_tool",
            new_callable=AsyncMock,
            return_value=MOCK_SUPPLIERS,
        ):
            import uvo_gui.pages.suppliers  # noqa: F401

            await user.open("/suppliers")
            await user.should_see("Dodavatelia")
            table = user.find(kind=ui.table).elements.pop()
            names = [r.get("name") for r in table.rows]
            assert "ACME Stavby s.r.o." in names
            assert "IT Solutions a.s." in names
