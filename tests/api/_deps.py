"""Context-manager form of FastAPI dependency overrides for the API tests."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any


def _apps(client) -> list:
    app = client.app
    v1_app = getattr(app.state, "v1_app", None)
    return [app] if v1_app is None else [app, v1_app]


@contextmanager
def deps(client, dependency: Callable, value: Any) -> Iterator[None]:
    """Serve ``value`` for ``dependency`` on the app and its mounted /v1 sub-app.

    Dependency overrides are per-app, and /v1 is a mounted sub-app, so both are set.
    """
    provider = lambda: value  # noqa: E731
    apps = _apps(client)
    for app in apps:
        app.dependency_overrides[dependency] = provider
    try:
        yield
    finally:
        for app in apps:
            app.dependency_overrides.pop(dependency, None)
