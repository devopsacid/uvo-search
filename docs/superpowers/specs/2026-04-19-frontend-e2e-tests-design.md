# Frontend E2E Tests — Design

Date: 2026-04-19
Branch: `feature/e2e-frontend-tests`

## Goal

Add real-browser end-to-end tests covering both frontends, running against the full docker-compose stack. Complements existing HTTP-level smoke tests in `tests/e2e/`.

## Scope

Two frontends:
- **Vue admin GUI** — `src/uvo-gui-vuejs`, nginx at `http://localhost:3000`. Routes: `/`, `/contracts`, `/suppliers`, `/suppliers/:ico`, `/procurers`, `/procurers/:ico`, `/costs`, `/search`.
- **NiceGUI search app** — `src/uvo_gui`, Python at `http://localhost:8080`. Pages: search, suppliers, procurers, graph, about.

## Stack

- **Playwright Python** via `pytest-playwright` (aligns with existing Python test infra).
- Headless Chromium only (Firefox/WebKit are YAGNI right now).
- Reuse the existing docker-compose fixture pattern.
- All tests marked `@pytest.mark.e2e` (deselect with `-m "not e2e"`).

## Structure

```
tests/e2e/
├── conftest.py                    # NEW — session-scoped compose fixture + playwright helpers
├── test_docker_compose.py         # existing (unchanged logic, adopt shared compose fixture)
├── test_vue_admin_gui.py          # existing (unchanged logic, adopt shared compose fixture)
├── test_vue_admin_browser.py      # NEW — Playwright tests for Vue SPA
└── test_nicegui_browser.py        # NEW — Playwright tests for NiceGUI
```

### Shared fixture contract

In `tests/e2e/conftest.py`:

- `compose_stack` — `session`-scoped. Builds + starts docker-compose, waits for all
  four service healthchecks (mcp :8000, api :8001, admin-gui :3000, gui :8080),
  yields, tears down with `down -v`. Replaces the per-module fixtures in the two
  existing files.
- Standard pytest-playwright fixtures (`page`, `browser_context_args`) are used
  as-is. `browser_context_args` overridden to set `base_url` at the test level.

The two existing files are updated to consume `compose_stack` instead of
defining their own `docker_compose_up`.

## Test Matrix

### `test_vue_admin_browser.py`

- **Dashboard loads** — navigate to `/`, assert page title or a visible sentinel
  (e.g. "Dashboard" heading), no console errors.
- **Nav links present** — header/sidebar shows links to Contracts, Suppliers,
  Procurers, Costs, Search.
- **Contracts page** — click contracts link, URL becomes `/contracts`, table or
  empty-state placeholder renders.
- **Suppliers list → detail** — navigate to `/suppliers`, click first row if
  present (or skip with a reason), URL matches `/suppliers/<ico>`, detail page
  renders without error.
- **Procurers list** — `/procurers` renders, list or empty state visible.
- **SPA deep link** — direct navigation to `/suppliers/12345` renders the detail
  shell (nginx fallback behavior verified at browser level, not just HTTP).
- **API proxy works in-browser** — open `/contracts`, wait for `/api/contracts`
  XHR response, assert 200.
- **No console errors during nav** — a `page.on("pageerror", ...)` listener
  collects errors across a click-through; assert empty at the end.

### `test_nicegui_browser.py`

- **Root loads** — navigate to `/`, assert "UVO Search" in page, NiceGUI
  scaffolding (`<script ... socket.io ...>`) present.
- **Search flow** — locate the search input, type a query (e.g. "softvér"),
  submit, assert either results rows appear or an empty-state message renders
  within a timeout. Use a lenient assertion because live MCP data may be empty.
- **Tab navigation** — click Suppliers / Procurers / Graph / About tabs; each
  renders its respective landing content.
- **Detail drill-in (if search returns rows)** — click a result; detail panel
  opens without console errors.
- **Robustness** — attach `page.on("pageerror")`; flow should not emit uncaught
  JS errors.

Tests that depend on live data ("if search returns rows") gracefully skip when
the data isn't available, rather than failing flakily. The assertion is always
"either A or B renders" — both are success.

## Dependencies

Add to `[project.optional-dependencies].dev` in `pyproject.toml`:

- `pytest-playwright>=0.5` (pulls in `playwright`)

Chromium browser binary is installed via `playwright install chromium --with-deps`
— documented in the test file docstring and in `README.md` under test setup.

## Timeouts & reliability

- Default Playwright timeout: 15s (generous — CI runners are slow).
- Compose startup: reuse existing 120s per-service.
- Tests retry at most once via `--reruns 1` (if flake appears). No retries by
  default — prefer fixing the test.

## Running

```bash
# Install browser once
uv run playwright install chromium --with-deps

# Run all e2e (HTTP + browser)
uv run pytest tests/e2e/ -m e2e -v

# Run browser tests only
uv run pytest tests/e2e/test_vue_admin_browser.py tests/e2e/test_nicegui_browser.py -v

# Default run excludes e2e
uv run pytest tests/ -v
```

## Out of scope

- Multi-browser coverage (Firefox/WebKit).
- Visual regression / screenshot diffing.
- Accessibility audits (axe-core).
- Parallel test execution within a single compose stack.
- Per-test data seeding (tests tolerate empty data).

## Approval

Auto-approved under auto mode + explicit "apply in worktree with subagents"
directive from the user.
