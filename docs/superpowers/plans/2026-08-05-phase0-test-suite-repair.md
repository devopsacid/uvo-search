# Phase 0 — Test Suite Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the API test suite to a state where it actually validates production behaviour, and gate lint/format in CI so drift cannot recur.

**Architecture:** No production code changes. The 18 failing tests fail because test fixtures encode a stale MCP response contract (`"data"`) that production abandoned in favour of `"items"`, and because two tests build `MagicMock()` without pinning `.isError`. We fix the fixtures, add a contract-guard test that fails loudly if the MCP payload shape ever drifts again, then wire `ruff` into CI.

**Tech Stack:** Python 3.12, uv, pytest, pytest-asyncio, ruff, GitHub Actions.

## Global Constraints

- Python 3.12+; all commands run through `uv run`, never raw `pip`/`python`.
- Do **not** modify anything under `src/` in this plan. If a test failure appears to be a genuine production bug, stop and report it rather than changing `src/`.
- Formatting is `ruff format` defaults (4-space indent, 100 col as configured in `pyproject.toml`).
- Commit after every task. Conventional Commits format (`fix:`, `test:`, `ci:`, `chore:`).
- Never run `tests/e2e/` in this plan — it requires `docker compose up`.

---

### Task 1: Establish the real MCP response contract

**Files:**
- Read: `src/uvo_mcp/tools/subjects.py`, `src/uvo_mcp/tools/procurements.py`
- Create: `tests/api/test_mcp_contract.py`

**Interfaces:**
- Produces: `MCP_LIST_KEYS` — a frozenset constant `{"items", "total"}` importable by later tasks as `from tests.api.test_mcp_contract import MCP_LIST_KEYS`. Later tasks rely on this being the authoritative shape.

- [ ] **Step 1: Confirm the actual payload keys before writing anything**

Run:
```bash
uv run python - <<'PY'
import inspect, re
from uvo_mcp.tools import subjects, procurements
for mod in (subjects, procurements):
    src = inspect.getsource(mod)
    print(mod.__name__, sorted(set(re.findall(r'"(items|total|data)"\s*:', src))))
PY
```
Expected: prints `items` and `total` for both modules, and **not** `data`. If `data` appears, STOP — the premise of this plan is wrong; report before continuing.

- [ ] **Step 2: Write the failing contract-guard test**

Create `tests/api/test_mcp_contract.py`:

```python
"""Guards the response contract between uvo_mcp tools and uvo_api routers.

If this test fails, an MCP tool changed its envelope keys. Update the routers
in src/uvo_api/routers/ AND every fixture in tests/api/ together — a drift
between them produces a test suite that passes while the API is broken.
"""

import inspect
import re

from uvo_mcp.tools import procurements, subjects

MCP_LIST_KEYS = frozenset({"items", "total"})


def _envelope_keys(module) -> set[str]:
    """Return the set of dict literal keys that look like list-envelope keys."""
    source = inspect.getsource(module)
    return set(re.findall(r'"(items|total|data)"\s*:', source))


def test_subjects_uses_items_envelope():
    keys = _envelope_keys(subjects)
    assert "items" in keys, "subjects tools must return an 'items' list"
    assert "data" not in keys, "subjects tools must not reintroduce the legacy 'data' key"


def test_procurements_uses_items_envelope():
    keys = _envelope_keys(procurements)
    assert "items" in keys, "procurements tools must return an 'items' list"
    assert "data" not in keys, "procurements tools must not reintroduce the legacy 'data' key"
```

- [ ] **Step 3: Run it to confirm it passes against current production code**

Run: `uv run pytest tests/api/test_mcp_contract.py -v`
Expected: 2 passed. (This test is a guard, not a red-green cycle — it documents the contract that Tasks 2–5 will align fixtures to.)

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_mcp_contract.py
git commit -m "test: add MCP response envelope contract guard"
```

---

### Task 2: Fix procurers fixtures

**Files:**
- Modify: `tests/api/test_procurers.py:9-33` (`SAMPLE_PROCURER_RESPONSE`, `SAMPLE_CONTRACTS_FOR_PROCURER`)

**Interfaces:**
- Consumes: `MCP_LIST_KEYS` contract from Task 1 (`items`/`total`).
- Produces: nothing later tasks import; the fixture-rename pattern established here is repeated verbatim in Tasks 3–5.

- [ ] **Step 1: Run the failing tests to capture the baseline**

Run: `uv run pytest tests/api/test_procurers.py -v`
Expected: FAIL — `test_list_procurers` with `IndexError`, `test_get_procurer_detail` and `test_get_procurer_summary` with `assert 404 == 200`.

- [ ] **Step 2: Rename the envelope key in both fixtures**

In `tests/api/test_procurers.py`, change the top-level key `"data"` to `"items"` in **both** module-level fixtures. After the edit the constants read:

```python
SAMPLE_PROCURER_RESPONSE = {
    "items": [
        {
            "ico": "12345678",
            "nazov": "Ministry of Finance",
            "pocet_zakaziek": 20,
            "celkova_hodnota": 10000000.0,
        },
    ],
    "total": 1,
}

SAMPLE_CONTRACTS_FOR_PROCURER = {
    "items": [
        {
            "id": "2001",
            "nazov": "Cloud Services",
            "obstaravatel": {"ico": "12345678", "nazov": "Ministry of Finance"},
            "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
            "hodnota_zmluvy": 300000.0,
            "datum_zverejnenia": "2023-03-10",
            "cpv_kod": "72000000",
        }
    ],
    "total": 1,
}
```

- [ ] **Step 3: Search the file for any remaining `"data"` envelope usage**

Run: `grep -n '"data"' tests/api/test_procurers.py`
Expected: no output. If a match remains inside a *nested* document (not the envelope), leave it — only the top-level list key changes.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/api/test_procurers.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_procurers.py
git commit -m "fix(tests): align procurer fixtures with items/total MCP envelope"
```

---

### Task 3: Fix suppliers fixtures

**Files:**
- Modify: `tests/api/test_suppliers.py` (module-level `SAMPLE_*` constants)

**Interfaces:**
- Consumes: the same `items`/`total` envelope as Task 2.

- [ ] **Step 1: Run the failing tests to capture the baseline**

Run: `uv run pytest tests/api/test_suppliers.py -v`
Expected: FAIL — `test_list_suppliers` (`assert 0 == 2`), `test_get_supplier_detail` and `test_get_supplier_summary` (`assert 404 == 200`).

- [ ] **Step 2: Locate every envelope key in the file**

Run: `grep -n '^\s*"data":' tests/api/test_suppliers.py`
Expected: one line per module-level fixture constant. Note the line numbers.

- [ ] **Step 3: Rename each of those `"data"` keys to `"items"`**

Edit only the lines found in Step 2 — the top-level list key of each `SAMPLE_*` dict. Leave nested document fields untouched. Example of the shape after editing:

```python
SAMPLE_SUPPLIER_RESPONSE = {
    "items": [
        {
            "ico": "87654321",
            "nazov": "Tech Corp",
            "pocet_zakaziek": 12,
            "celkova_hodnota": 4500000.0,
        },
    ],
    "total": 1,
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/api/test_suppliers.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_suppliers.py
git commit -m "fix(tests): align supplier fixtures with items/total MCP envelope"
```

---

### Task 4: Fix contracts fixtures

**Files:**
- Modify: `tests/api/test_contracts.py` (module-level `SAMPLE_*` constants)

- [ ] **Step 1: Run the failing tests to capture the baseline**

Run: `uv run pytest tests/api/test_contracts.py -v`
Expected: FAIL — `test_list_contracts_returns_paginated_response`, `test_list_contracts_maps_fields_correctly`, `test_get_contract_detail_returns_detail`.

- [ ] **Step 2: Locate every envelope key**

Run: `grep -n '^\s*"data":' tests/api/test_contracts.py`
Expected: one line per module-level fixture constant.

- [ ] **Step 3: Rename each of those `"data"` keys to `"items"`**

Edit only those lines. Do not alter nested keys such as `obstaravatel` or `dodavatelia`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/api/test_contracts.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_contracts.py
git commit -m "fix(tests): align contract fixtures with items/total MCP envelope"
```

---

### Task 5: Fix dashboard fixtures and the under-mocked summary test

**Files:**
- Modify: `tests/api/test_dashboard.py` (module-level fixtures + `test_dashboard_summary`)
- Modify: `tests/api/test_dashboard_ingestion.py` (`test_timeseries_counts_ingested_today`)
- Read: `src/uvo_api/routers/dashboard.py:79-137`

**Interfaces:**
- Consumes: the `items`/`total` envelope from Task 1.

`test_dashboard_summary` fails differently from the rest: `StopAsyncIteration`. The route issues **three** sequential `call_tool` awaits (contracts sample, `find_supplier`, `find_procurer`) but the test supplies only two `side_effect` values, so the third `await` exhausts the iterator.

- [ ] **Step 1: Run the failing tests to capture the baseline**

Run: `uv run pytest tests/api/test_dashboard.py tests/api/test_dashboard_ingestion.py -v`
Expected: FAIL — 7 failures including `test_dashboard_summary` with `StopAsyncIteration`.

- [ ] **Step 2: Count the real `call_tool` invocations in the route**

Run: `grep -n "call_tool" src/uvo_api/routers/dashboard.py`
Expected: shows the call inside `_fetch_contracts_sample` plus the `find_supplier` and `find_procurer` calls in `dashboard_summary`. Record the exact tool names and their order — the `side_effect` list must match that order.

- [ ] **Step 3: Rename the envelope keys in the module-level fixtures**

Run `grep -n '^\s*"data":' tests/api/test_dashboard.py` and change each of those top-level keys to `"items"`, exactly as in Task 2.

- [ ] **Step 4: Add the missing third side_effect value to `test_dashboard_summary`**

The `side_effect` list must have one entry per `await call_tool(...)` in call order. `_fetch_contracts_sample` loops `_AGG_PAGES` times, so it consumes that many entries before the entity lookups. Make the mock order-independent instead of positional — replace the `side_effect` **list** with a dispatch function keyed on tool name, which cannot go stale when the route adds a call:

```python
def _dispatch(tool_name, arguments):
    """Return a fixture per tool name, so call ordering/count can change freely."""
    return {
        "search_completed_procurements": SAMPLE_CONTRACTS_RESPONSE,
        "find_supplier": SAMPLE_SUPPLIERS_RESPONSE,
        "find_procurer": SAMPLE_PROCURERS_RESPONSE,
    }[tool_name]


def test_dashboard_summary(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(side_effect=_dispatch)):
        response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert "total_contracts" in body
```

Substitute the real fixture constant names present in the file for `SAMPLE_CONTRACTS_RESPONSE` / `SAMPLE_SUPPLIERS_RESPONSE` / `SAMPLE_PROCURERS_RESPONSE`, and the real assertion keys returned by the route. If a tool name in the route is missing from the dict, the `KeyError` names it explicitly — add it.

- [ ] **Step 5: Apply the same envelope rename to `test_dashboard_ingestion.py`**

Run: `grep -n '^\s*"data":' tests/api/test_dashboard_ingestion.py` and rename those top-level keys to `"items"`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/api/test_dashboard.py tests/api/test_dashboard_ingestion.py -v`
Expected: all passed, no `StopAsyncIteration`.

- [ ] **Step 7: Commit**

```bash
git add tests/api/test_dashboard.py tests/api/test_dashboard_ingestion.py
git commit -m "fix(tests): align dashboard fixtures with MCP envelope and dispatch mocks by tool name"
```

---

### Task 6: Fix the `mcp_client` mock truthiness bug

**Files:**
- Modify: `tests/api/test_mcp_client.py`
- Read: `src/uvo_api/mcp_client.py:23-43`

`call_tool` checks `if result.isError:` at `mcp_client.py:36`. A bare `MagicMock()` returns a **truthy child mock** for any unset attribute, so the "success" path raises `McpToolError` and both tests fail. The fix is to pin `.isError` explicitly on every mock result.

- [ ] **Step 1: Run the failing tests to capture the baseline**

Run: `uv run pytest tests/api/test_mcp_client.py -v`
Expected: FAIL — `test_call_tool_returns_parsed_json` and `test_call_tool_raises_on_no_text_content`.

- [ ] **Step 2: Pin `isError` on every mock result in the file**

For every place the test builds a mock tool result, set the flag explicitly. The success-path mock:

```python
mock_result = MagicMock()
mock_result.isError = False
mock_content = MagicMock()
mock_content.text = '{"items": [], "total": 0}'
mock_result.content = [mock_content]
```

For `test_call_tool_raises_on_no_text_content`, the content list must contain an object with **no** `text` attribute, so `hasattr(c, "text")` is False — a bare `MagicMock()` always has `text`. Use a plain object:

```python
class _NoText:
    """Content block without a .text attribute, so hasattr(c, 'text') is False."""

mock_result = MagicMock()
mock_result.isError = False
mock_result.content = [_NoText()]
```

- [ ] **Step 3: Run the tests to verify they pass**

Run: `uv run pytest tests/api/test_mcp_client.py -v`
Expected: 2 passed.

- [ ] **Step 4: Add a regression test pinning the error path**

Append to `tests/api/test_mcp_client.py`:

```python
@pytest.mark.asyncio
async def test_call_tool_raises_when_is_error_true(monkeypatch):
    """isError=True must raise McpToolError even when the payload parses cleanly."""
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")

    mock_result = MagicMock()
    mock_result.isError = True
    mock_content = MagicMock()
    mock_content.text = '{"error": "MongoDB not configured", "status_code": 503}'
    mock_result.content = [mock_content]

    mock_session = AsyncMock()
    mock_session.call_tool.return_value = mock_result

    with patch("uvo_api.mcp_client.ClientSession") as session_cls, patch(
        "uvo_api.mcp_client.streamablehttp_client"
    ) as http_client:
        http_client.return_value.__aenter__.return_value = (None, None, None)
        session_cls.return_value.__aenter__.return_value = mock_session
        with pytest.raises(McpToolError):
            await call_tool("find_procurer", {})
```

Ensure `McpToolError`, `call_tool`, `AsyncMock`, and `pytest` are imported at the top of the file; add any missing import.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/api/test_mcp_client.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/api/test_mcp_client.py
git commit -m "fix(tests): pin isError on mcp_client mocks and cover the error path"
```

---

### Task 7: Full suite green + lint/format cleanup

**Files:**
- Modify: every file `ruff` flags under `src/` and `tests/`

- [ ] **Step 1: Run the full non-e2e suite**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -v`
Expected: 0 failed. If anything still fails, fix it before proceeding — do not lint on top of a red suite.

- [ ] **Step 2: Auto-fix lint findings**

Run: `uv run ruff check --fix src/ tests/`
Expected: reports the 57 auto-fixable findings resolved (unsorted imports `I001`, unused imports `F401`).

- [ ] **Step 3: Resolve any remaining manual findings**

Run: `uv run ruff check src/ tests/`
Expected: no output. If a finding remains, fix it in place. Do not add blanket `# noqa`; if a suppression is genuinely correct, use a rule-specific `# noqa: RULE` with a trailing comment explaining why.

- [ ] **Step 4: Apply formatting**

Run: `uv run ruff format src/ tests/`
Expected: reports ~54 files reformatted.

- [ ] **Step 5: Re-run the suite to prove formatting changed no behaviour**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: same pass count as Step 1, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add -u
git commit -m "style: apply ruff check --fix and ruff format across src and tests"
```

---

### Task 8: Gate lint, format, and tests in CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Read the existing workflow to find the job to extend**

Run: `cat -n .github/workflows/ci.yml`
Expected: shows an existing job that sets up Python/uv. Note its `name:` and the step that runs `uv sync`.

- [ ] **Step 2: Add lint and format gates immediately after the dependency-install step**

Insert into the existing test job, after `uv sync`:

```yaml
      - name: Lint (ruff check)
        run: uv run ruff check src/ tests/

      - name: Format check (ruff format)
        run: uv run ruff format --check src/ tests/

      - name: Unit tests
        run: uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q
```

Keep indentation consistent with the surrounding steps in the file. Do not add `continue-on-error` — the point of this task is that the gate fails the build.

- [ ] **Step 3: Verify the exact commands pass locally before pushing**

Run:
```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q
```
Expected: exit code 0. Confirm with `echo $?`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: gate ruff check, ruff format, and unit tests"
```

---

## Done when

- `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/` reports 0 failures.
- `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/` both exit 0.
- CI fails if any of the three gates regress.
- No file under `src/` was modified by this plan.
