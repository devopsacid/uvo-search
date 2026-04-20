# UVO Search — Claude Context

Search and browse Slovak government procurement data. Shared MCP backend, multiple frontends.

## Architecture

Five Python packages under `src/` + one Vue app:

| Package | Port | Entrypoint | Role |
| ------- | ---- | ---------- | ---- |
| `uvo_mcp` | 8000 | `uv run python -m uvo_mcp` | FastMCP server — search, detail, graph tools |
| `uvo_api` | 8001 | `uv run python -m uvo_api` | FastAPI bridge (admin-gui → MCP) |
| `uvo_gui` | 8080 | `uv run python -m uvo_gui` | NiceGUI public frontend (Slovak UI) |
| `uvo_pipeline` | — | `uv run python -m uvo_pipeline` | One-shot ingestion (UVO/CRZ/ITMS/TED/NKOD → Mongo/Neo4j) |
| `uvo-gui-vuejs` | 5173 dev / 3000 prod | `cd src/uvo-gui-vuejs && npm run dev` | Vue 3 admin dashboard |

**Storage:** MongoDB Atlas Local (27017, with `mongot` for Atlas Search) + Neo4j 5 with APOC (7474/7687). Both required for `uvo_mcp` to start.

**Frontend ↔ backend:** both GUIs go through `mcp_client.call_tool(name, args)`. Don't bypass it.

## Dev commands

Python 3.12+ (see `pyproject.toml`). Use **uv**, not raw pip.

```bash
# Setup
uv sync --all-extras                        # install deps incl. dev
cp .env.example .env                        # edit secrets before first run

# Run services natively (each in its own terminal)
uv run python -m uvo_mcp
uv run python -m uvo_api
uv run python -m uvo_gui
cd src/uvo-gui-vuejs && npm install && npm run dev

# Tests
uv run pytest tests/mcp/ tests/gui/ -v      # unit (mocked) — run these, not `tests/`
uv run pytest tests/api/ tests/pipeline/ -v
uv run pytest tests/e2e/ -v                 # requires docker compose up
uv run pytest --cov=src -v

# Lint
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Vue
cd src/uvo-gui-vuejs && npm run test
```

## Docker (local deploy)

Full stack (mcp + api + gui + admin-gui + mongo + neo4j + pipeline) lives in `docker-compose.yml`. For build/deploy/troubleshoot operations, use the `docker-troubleshoot` skill (`.claude/skills/docker-troubleshoot/`) or the `/docker` slash command. Don't reinvent — it already covers port conflicts, healthcheck debugging, mongo/neo4j volume-init gotchas, service-name URIs, and nuclear-reset tiers.

## Workflow

- New features: use `superpowers:using-git-worktrees` to create an isolated worktree before writing code. Skip for single-file fixes, docs-only edits, or changes to the in-progress branch.
- Non-trivial multi-phase work (design + build + test): prefer the `/team` skill over ad-hoc subagent spawns.

## NiceGUI 3.9 gotchas

- `ui.page_container` does not exist — use `ui.column().classes("w-full h-full")` as content wrapper.
- Async from sync handlers: `asyncio.ensure_future(coro())`, not `ui.timer(0, ..., once=True)`.
- Module-level `_state = StateClass()` is the established page-state pattern.
- `@ui.refreshable` functions called from state methods is the established refresh pattern.

## NiceGUI testing

- User API: `should_see` / `should_not_see` — `should_contain` does not exist.
- Click events do NOT bubble — attach `.on("click", ...)` to the element `user.find()` targets.
- `pytest_plugins = ["nicegui.testing.general_fixtures"]` belongs in the **root** `conftest.py` only. Putting it in a subdirectory conftest breaks `pytest tests/` collection — which is why unit tests are run as `tests/mcp/ tests/gui/` explicitly.
- Layout-isolated tests use the `layout_user` fixture + `tests/gui/layout_test_app.py`.

## Data / search gotchas

- Mongo uses a custom `sk_folding` analyzer (standard tokenizer + `lowercase` + `icuFolding`) for case- and diacritic-insensitive Slovak search. Name fields carry an `autocomplete` (edgeGram) subfield powering the live dropdown.
- Atlas Search indexes are created on `uvo_mcp` startup — expect a cold-start lag on a fresh Mongo volume.
- Legacy-data migration after Mongo image swap: `scripts/migrate_to_atlas_local.sh` (one-shot).
- Graph page (`/graph` in NiceGUI) depends on Neo4j + `graph_ego_network` / `graph_cpv_network` MCP tools; if Neo4j is down the page will error, not silently degrade.

## Secrets & env

`.env` keys that matter: `STORAGE_SECRET`, `MONGO_PASSWORD`, `NEO4J_PASSWORD`, `EKOSYSTEM_API_TOKEN` (optional). Inside containers, URIs must reference service names (`mongo`, `neo4j`, `mcp-server`) — never `localhost`. See the `docker-troubleshoot` skill for the full list.
