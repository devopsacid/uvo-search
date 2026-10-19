"""Shared fixtures for the API tests.

The API no longer has module-level clients: routers receive them through FastAPI
dependencies backed by ``app.state.resources``. Tests therefore never need to patch
``get_db`` & co. in router modules; they either rely on the inert resources below or
swap a dependency through the ``override`` fixture.
"""

from unittest.mock import MagicMock

import fakeredis.aioredis
import pytest

from uvo_api import db as api_db


@pytest.fixture(autouse=True)
def _inert_resources(monkeypatch):
    """Make the lazy no-lifespan fallback build offline fakes instead of real clients.

    A handler that touches the (MagicMock) database without the test mocking the call
    fails loudly instead of hanging on a connection attempt.
    """

    def _build(settings):
        return api_db.Resources(
            mongo_client=MagicMock(name="mongo_client"),
            db=MagicMock(name="db"),
            redis=fakeredis.aioredis.FakeRedis(decode_responses=True),
            neo4j_driver=None,
        )

    monkeypatch.setattr(api_db, "build_resources", _build)


@pytest.fixture
def override(client):
    """``override(dependency, value)``: serve ``value`` for ``dependency`` on the app and /v1.

    Uses the test module's ``client`` fixture. Dependency overrides are per-app, and
    /v1 is a mounted sub-app, so the override is applied to both.
    """
    app = client.app

    def _override(dependency, value):
        provider = lambda: value  # noqa: E731
        app.dependency_overrides[dependency] = provider
        v1_app = getattr(app.state, "v1_app", None)
        if v1_app is not None:
            v1_app.dependency_overrides[dependency] = provider

    yield _override
    app.dependency_overrides.clear()
    v1_app = getattr(app.state, "v1_app", None)
    if v1_app is not None:
        v1_app.dependency_overrides.clear()
