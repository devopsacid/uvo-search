"""Tests for the O aplikácii page."""

import pytest
from nicegui.testing import User


@pytest.mark.asyncio
async def test_about_page_renders_content(user: User) -> None:
    import uvo_gui.pages.about  # noqa: F401

    await user.open("/about")
    await user.should_see("O aplikácii UVO Search")
    await user.should_see("uvo.gov.sk")
