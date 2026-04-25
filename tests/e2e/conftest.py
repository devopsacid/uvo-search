"""Shared fixtures for e2e tests.

Provides a session-scoped ``compose_stack`` fixture that builds + starts the
full docker-compose stack and tears it down after the session.  All four
services must be healthy before the fixture yields:

- MCP server    http://localhost:8000/health
- Analytics API http://localhost:8001/health
- Admin GUI     http://localhost:3000
- React GUI     http://localhost:8080

Also overrides pytest-playwright's ``browser_context_args`` to set a
reasonable viewport and silence https errors on localhost.
"""

import subprocess
import time

import httpx
import pytest

COMPOSE_FILE = "docker-compose.yml"

HEALTH_CHECKS = [
    ("MCP server", "http://localhost:8000/health"),
    ("Analytics API", "http://localhost:8001/health"),
    ("Admin GUI", "http://localhost:3000"),
    ("React GUI", "http://localhost:8080"),
]

STARTUP_TIMEOUT = 120
POLL_INTERVAL = 3


def _wait_for_health(url: str, timeout: int) -> bool:
    """Poll *url* until it returns HTTP 200 or *timeout* seconds elapse."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=5)
            if resp.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
            pass
        time.sleep(POLL_INTERVAL)
    return False


def _dump_logs():
    """Print the last 50 lines of docker compose logs for debugging."""
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "logs", "--tail=50"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    print("=== Docker Compose Logs ===")
    print(result.stdout)
    if result.stderr:
        print(result.stderr)


@pytest.fixture(scope="session")
def compose_stack():
    """Build + start docker-compose stack; yield; tear down with ``down -v``."""
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "build"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(f"docker compose build failed:\n{result.stderr}")

    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(f"docker compose up failed:\n{result.stderr}")

    for name, url in HEALTH_CHECKS:
        if not _wait_for_health(url, STARTUP_TIMEOUT):
            _dump_logs()
            subprocess.run(
                ["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"], timeout=30
            )
            pytest.fail(f"{name} did not become healthy within {STARTUP_TIMEOUT}s")

    yield

    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"],
        capture_output=True,
        timeout=30,
    )


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Override default playwright context: 1280×800 viewport, ignore https errors."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 800},
        "ignore_https_errors": True,
    }
