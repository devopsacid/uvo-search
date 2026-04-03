"""Pytest configuration for NiceGUI frontend tests."""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from nicegui.testing import User
from nicegui.testing.user_simulation import user_simulation

pytest_plugins = ["nicegui.testing.general_fixtures"]

LAYOUT_TEST_APP = Path(__file__).parent / "layout_test_app.py"


@pytest.fixture
async def user(caplog: pytest.LogCaptureFixture) -> AsyncGenerator[User, None]:
    """Provide a NiceGUI test user with an isolated app context (no main file)."""
    async with user_simulation() as u:
        yield u

        logs = [r for r in caplog.get_records("call") if r.levelname == "ERROR"]
        if logs:
            pytest.fail("There were unexpected ERROR logs.", pytrace=False)


@pytest.fixture
async def layout_user(caplog: pytest.LogCaptureFixture) -> AsyncGenerator[User, None]:
    """Provide a NiceGUI test user with the layout test app registered."""
    async with user_simulation(main_file=LAYOUT_TEST_APP) as u:
        yield u

        logs = [r for r in caplog.get_records("call") if r.levelname == "ERROR"]
        if logs:
            pytest.fail("There were unexpected ERROR logs.", pytrace=False)
