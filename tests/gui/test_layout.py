"""Tests for the shared Quasar layout component."""

import pytest
from nicegui.testing import User


@pytest.mark.asyncio
async def test_layout_renders_app_name(layout_user: User) -> None:
    await layout_user.open("/test-layout")
    await layout_user.should_see("UVO Search")


@pytest.mark.asyncio
async def test_layout_renders_all_nav_links(layout_user: User) -> None:
    await layout_user.open("/test-layout")
    await layout_user.should_see("Vyhľadávanie")
    await layout_user.should_see("Obstaravatelia")
    await layout_user.should_see("Dodavatelia")
    await layout_user.should_see("O aplikácii")
