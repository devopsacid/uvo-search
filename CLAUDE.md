# UVO Search — Claude Context

## Project
Two-process app: NiceGUI frontend (port 8080) + FastMCP server (port 8000).
Frontend calls backend via `mcp_client.call_tool(tool_name, arguments)`.

## Workflow

- New features: use `superpowers:using-git-worktrees` to create an isolated worktree before writing code. Skip for single-file fixes, docs-only edits, or changes to the current in-progress branch.

## Dev Commands
- `pytest tests/gui/ -v` — GUI tests
- `pytest tests/mcp/ -v` — MCP/backend tests
- `pytest tests/gui/ tests/mcp/ -v` — all tests (run separately, not `tests/` root — see below)

## NiceGUI 3.9 Gotchas
- `ui.page_container` does not exist — use `ui.column().classes("w-full h-full")` as content wrapper
- Async from sync handlers: `asyncio.ensure_future(coro())` not `ui.timer(0, ..., once=True)`
- Module-level `_state = StateClass()` is the established page state pattern
- `@ui.refreshable` functions called from state methods is the established refresh pattern

## Testing (NiceGUI)
- User API: `should_see` / `should_not_see` — `should_contain` does not exist
- Click events do NOT bubble — attach `.on("click", ...)` to the element `user.find()` targets
- `pytest_plugins = ["nicegui.testing.general_fixtures"]` belongs in root `conftest.py` only
  (placing it in a subdirectory conftest breaks `pytest tests/` collection)
- Layout-isolated tests use `layout_user` fixture + `tests/gui/layout_test_app.py`
