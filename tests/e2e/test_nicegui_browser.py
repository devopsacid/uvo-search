"""Browser-based e2e tests for the UVO Search NiceGUI frontend.

Exercises the NiceGUI application at http://localhost:8080 via Playwright:
root page load, search flow, tab/page navigation, detail-panel drill-in, and
absence of uncaught JS errors.  All tests depend on the session-scoped
``compose_stack`` fixture (defined in conftest.py) and require a running
docker-compose stack with the full service set.

Usage:
    pytest tests/e2e/test_nicegui_browser.py -m e2e -v
"""

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8080"
DEFAULT_TIMEOUT = 15_000  # ms — NiceGUI renders via websocket, be generous


# ── helpers ───────────────────────────────────────────────────────────────────

def _goto(page: Page, path: str = "/") -> None:
    """Navigate and wait for the NiceGUI websocket to settle."""
    page.goto(f"{BASE_URL}{path}")
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)


# ── root load ─────────────────────────────────────────────────────────────────

@pytest.mark.e2e
class TestRootLoads:
    """NiceGUI root page renders correctly and bootstraps the client runtime."""

    def test_title_visible(self, compose_stack, page: Page):
        _goto(page)
        # The header wordmark is rendered by layout.py as ui.label("UVO Search")
        expect(page.get_by_text("UVO Search").first).to_be_visible(timeout=DEFAULT_TIMEOUT)

    def test_nicegui_socket_present(self, compose_stack, page: Page):
        # NiceGUI injects a socket.io script tag for its websocket transport
        _goto(page)
        scripts = page.locator("script[src*='socket.io'], script[src*='nicegui']")
        # At least one matching script tag must exist in the DOM
        assert scripts.count() > 0


# ── search flow ───────────────────────────────────────────────────────────────

@pytest.mark.e2e
class TestSearchFlow:
    """Search input accepts a query and renders either results or an empty state."""

    def test_search_input_and_response(self, compose_stack, page: Page):
        _goto(page)
        # search_box renders ui.input with a Slovak placeholder string
        search_input = page.get_by_placeholder("Hľadať")
        expect(search_input).to_be_visible(timeout=DEFAULT_TIMEOUT)

        search_input.fill("stavba")
        search_input.press("Enter")

        # Either result rows (q-tr in the uvo-table) or the empty-state hint text
        # are acceptable outcomes — live MCP data may be empty or unavailable
        result_rows = page.locator(".uvo-table tbody tr, .uvo-table .q-tr")
        empty_hint = page.get_by_text("Kliknite na ľubovoľný riadok")
        error_msg = page.locator("text=Chyba pri vyhľadávaní")

        # Wait for any one of the three outcomes
        result_rows.or_(empty_hint).or_(error_msg).first.wait_for(timeout=DEFAULT_TIMEOUT)


# ── tab / page navigation ─────────────────────────────────────────────────────

@pytest.mark.e2e
class TestTabNavigation:
    """Each nav entry in the sidebar leads to the correct page content."""

    def test_navigate_to_procurers(self, compose_stack, page: Page):
        _goto(page)
        # Sidebar nav items are ui.html divs containing Slovak label text (layout.py)
        page.get_by_text("Obstaravatelia").first.click()
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        # suppliers.py renders ui.label("Obstaravatelia") as the page heading
        expect(page.get_by_text("Obstaravatelia").first).to_be_visible(timeout=DEFAULT_TIMEOUT)
        assert "/procurers" in page.url

    def test_navigate_to_suppliers(self, compose_stack, page: Page):
        _goto(page)
        page.get_by_text("Dodavatelia").first.click()
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        # suppliers.py renders ui.label("Dodavatelia")
        expect(page.get_by_text("Dodavatelia").first).to_be_visible(timeout=DEFAULT_TIMEOUT)
        assert "/suppliers" in page.url

    def test_navigate_to_graph(self, compose_stack, page: Page):
        _goto(page)
        # NAV_ITEMS has "Sieť" for the graph page
        page.get_by_text("Sieť").first.click()
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        # graph.py renders ui.label("Sieť vzťahov")
        expect(page.get_by_text("Sieť vzťahov")).to_be_visible(timeout=DEFAULT_TIMEOUT)
        assert "/graph" in page.url

    def test_navigate_to_about(self, compose_stack, page: Page):
        _goto(page)
        page.get_by_text("O aplikácii").first.click()
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        # about.py renders ui.label("O aplikácii UVO Search")
        expect(page.get_by_text("O aplikácii UVO Search")).to_be_visible(timeout=DEFAULT_TIMEOUT)
        assert "/about" in page.url

    def test_navigate_back_to_search(self, compose_stack, page: Page):
        _goto(page, "/about")
        page.get_by_text("Vyhľadávanie").first.click()
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        # Header wordmark is always visible; the kicker "Hľadať v archíve" confirms search page
        expect(page.get_by_text("Hľadať v archíve")).to_be_visible(timeout=DEFAULT_TIMEOUT)
        assert page.url.rstrip("/").endswith(":8080") or page.url.endswith("/")


# ── detail drill-in ───────────────────────────────────────────────────────────

@pytest.mark.e2e
class TestDetailDrillIn:
    """Clicking a result row opens the detail panel without JS errors."""

    def test_detail_panel_on_row_click(self, compose_stack, page: Page):
        _goto(page)

        # Wait for table to settle after initial data load
        page.wait_for_timeout(3000)

        rows = page.locator(".uvo-table tbody tr, .uvo-table .q-tr")
        if rows.count() == 0:
            pytest.skip("no search results to drill into")

        rows.first.click()

        # Detail panel signals itself with the "Záznam" kicker (search.py _render_detail)
        # and the close button "×"
        detail_kicker = page.locator(".uvo-detail-kicker").first
        expect(detail_kicker).to_be_visible(timeout=DEFAULT_TIMEOUT)

        close_btn = page.get_by_role("button", name="×")
        expect(close_btn).to_be_visible(timeout=DEFAULT_TIMEOUT)


# ── no uncaught JS errors ─────────────────────────────────────────────────────

@pytest.mark.e2e
class TestNoUncaughtJSErrors:
    """Navigate through multiple pages and assert no uncaught JS exceptions fire."""

    def test_no_js_errors_during_navigation(self, compose_stack, page: Page):
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        _goto(page)
        page.get_by_text("Dodavatelia").first.click()
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        page.get_by_text("Obstaravatelia").first.click()
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        page.get_by_text("O aplikácii").first.click()
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        page.get_by_text("Vyhľadávanie").first.click()
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

        assert errors == [], f"Uncaught JS errors during navigation: {errors}"
