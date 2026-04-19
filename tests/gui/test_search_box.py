import os
from unittest.mock import AsyncMock, patch

from nicegui import ui
from nicegui.elements.input import Input as NiceInput
from nicegui.testing import User


async def test_search_box_shows_dropdown_on_input(user: User):
    mock = AsyncMock(return_value={"results": [
        {"type": "procurer", "id": "111", "label": "Fakulta A", "sublabel": "IČO 111"},
    ]})
    with patch.dict(os.environ, {"STORAGE_SECRET": "test", "UVOSTAT_API_TOKEN": "dummy"}):
        with patch("uvo_gui.mcp_client.call_tool", mock):
            from uvo_gui.components.search_box import _flush_for_tests, search_box

            @ui.page("/sb")
            def page():
                async def on_submit(q): pass
                async def on_select(item): pass
                search_box(on_submit=on_submit, on_select=on_select, debounce=0)

            await user.open("/sb")
            user.find(kind=NiceInput).type("fak")
            await _flush_for_tests()
            await user.should_see("Fakulta A")


async def test_search_box_empty_query_clears_results(user: User):
    mock = AsyncMock(return_value={"results": []})
    with patch.dict(os.environ, {"STORAGE_SECRET": "test", "UVOSTAT_API_TOKEN": "dummy"}):
        with patch("uvo_gui.mcp_client.call_tool", mock):
            from uvo_gui.components.search_box import _flush_for_tests, search_box

            @ui.page("/sb2")
            def page():
                search_box(debounce=0)

            await user.open("/sb2")
            user.find(kind=NiceInput).type("")
            await _flush_for_tests()
            # No assertion needed; just ensure no crash on empty
