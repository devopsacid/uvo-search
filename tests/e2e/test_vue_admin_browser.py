"""Browser-based end-to-end tests for the Vue admin GUI (http://localhost:3000).

Uses pytest-playwright (Chromium headless) against the full docker-compose stack.
All tests require the ``compose_stack`` session fixture from conftest.py.

Before first run, install the browser binary once:
    uv run playwright install chromium --with-deps

Usage:
    uv run pytest tests/e2e/test_vue_admin_browser.py -m e2e -v
"""

import re

import pytest
from playwright.sync_api import Page, Response

BASE_URL = "http://localhost:3000"
DEFAULT_TIMEOUT = 15_000  # ms — generous for slow CI runners


@pytest.mark.e2e
def test_dashboard_loads(page: Page, compose_stack):
    """Root page renders visible content (h1 or nav element)."""
    page.goto(BASE_URL, timeout=DEFAULT_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
    # Either an h1 heading or the top-level nav must be visible
    h1 = page.locator("h1")
    nav = page.locator("nav")
    assert h1.count() > 0 or nav.count() > 0, "No h1 or nav found on dashboard"


@pytest.mark.e2e
def test_nav_links_present(page: Page, compose_stack):
    """Header/nav contains links for all primary routes."""
    page.goto(BASE_URL, timeout=DEFAULT_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    expected = ["Contracts", "Suppliers", "Procurers", "Costs", "Search"]
    for label in expected:
        link = page.get_by_role("link", name=re.compile(label, re.IGNORECASE))
        assert link.count() > 0, f"Nav link '{label}' not found"


@pytest.mark.e2e
def test_contracts_page_renders(page: Page, compose_stack):
    """Contracts page shows a table or an empty-state element."""
    page.goto(f"{BASE_URL}/contracts", timeout=DEFAULT_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    assert page.url.endswith("/contracts"), f"Unexpected URL: {page.url}"
    table = page.locator("table")
    empty = page.locator("[class*='empty'], [class*='no-data'], td:has-text('No'), p:has-text('No')")
    assert table.count() > 0 or empty.count() > 0, "Neither table nor empty-state found"


@pytest.mark.e2e
def test_suppliers_list_and_detail(page: Page, compose_stack):
    """Suppliers list renders; if rows present, clicking one opens detail view."""
    page.goto(f"{BASE_URL}/suppliers", timeout=DEFAULT_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    table = page.locator("table")
    empty = page.locator("[class*='empty'], [class*='no-data'], td:has-text('No'), p:has-text('No')")
    assert table.count() > 0 or empty.count() > 0, "Suppliers page has no table or empty-state"

    # If table rows exist, click the first data row and verify detail navigation
    rows = page.locator("table tbody tr")
    if rows.count() == 0:
        pytest.skip("No supplier rows in DB — skipping detail drill-in")

    rows.first.click()
    page.wait_for_url(re.compile(r"/suppliers/\d+"), timeout=DEFAULT_TIMEOUT)
    assert re.search(r"/suppliers/\d+", page.url), f"Detail URL unexpected: {page.url}"
    # Detail shell must have at least some visible content
    assert page.locator("h1, h2, [class*='detail'], [class*='card']").count() > 0


@pytest.mark.e2e
def test_procurers_page_renders(page: Page, compose_stack):
    """Procurers list page renders a table or empty-state."""
    page.goto(f"{BASE_URL}/procurers", timeout=DEFAULT_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    table = page.locator("table")
    empty = page.locator("[class*='empty'], [class*='no-data'], td:has-text('No'), p:has-text('No')")
    assert table.count() > 0 or empty.count() > 0, "Procurers page has no table or empty-state"


@pytest.mark.e2e
def test_spa_deep_link(page: Page, compose_stack):
    """Direct navigation to /suppliers/12345 renders the SPA shell in a real browser."""
    page.goto(f"{BASE_URL}/suppliers/12345", timeout=DEFAULT_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    # The SPA shell must mount — look for the Vue app root or any rendered element
    assert page.locator("#app").count() > 0, "#app mount point not found"
    # Page must not be a raw nginx 404
    assert "404" not in page.title().lower(), "Got a 404 page instead of SPA shell"


@pytest.mark.e2e
def test_api_proxy_in_browser(page: Page, compose_stack):
    """Navigate to /contracts and assert the browser receives a 200 from /api/contracts."""
    api_responses: list[Response] = []

    def capture(response: Response):
        if "/api/contracts" in response.url:
            api_responses.append(response)

    page.on("response", capture)
    page.goto(f"{BASE_URL}/contracts", timeout=DEFAULT_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    assert api_responses, "No /api/contracts request was made by the page"
    assert api_responses[0].status == 200, f"/api/contracts returned {api_responses[0].status}"


@pytest.mark.e2e
def test_no_console_errors_during_navigation(page: Page, compose_stack):
    """Click through main routes; assert no uncaught JS errors are thrown."""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    routes = ["/", "/contracts", "/suppliers", "/procurers", "/costs", "/search"]
    for route in routes:
        page.goto(f"{BASE_URL}{route}", timeout=DEFAULT_TIMEOUT)
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    assert errors == [], "Uncaught JS errors during navigation:\n" + "\n".join(errors)
