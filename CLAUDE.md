# UVO Search — Claude Context

Search and browse Slovak government procurement data. Shared MCP backend, single React frontend.

## Architecture

Four Python packages under `src/` + one React frontend:

| Package | Port | Entrypoint | Role |
| ------- | ---- | ---------- | ---- |
| `uvo_mcp` | 8000 | `uv run python -m uvo_mcp` | FastMCP server — search, detail, graph tools |
| `uvo_api` | 8001 | `uv run python -m uvo_api` | FastAPI bridge (frontend → MCP) |
| `uvo-gui-react` | 8080 host / 5174 dev | `cd src/uvo-gui-react && npm run dev` | React 18 SPA public frontend (Slovak UI) |
| `uvo_pipeline` | — | `uv run python -m uvo_pipeline` | One-shot ingestion (UVO/CRZ/ITMS/TED/NKOD → Mongo/Neo4j) |

**Storage:** MongoDB Atlas Local (27017, with `mongot` for Atlas Search) + Neo4j 5 with APOC (7474/7687). Both required for `uvo_mcp` to start.

**Frontend ↔ backend:** the GUI goes through `mcp_client.call_tool(name, args)`. Don't bypass it.

## Dev commands

Python 3.12+ (see `pyproject.toml`). Use **uv**, not raw pip.

```bash
# Setup
uv sync --all-extras                        # install deps incl. dev
cp .env.example .env                        # edit secrets before first run

# Run services natively (each in its own terminal)
uv run python -m uvo_mcp
uv run python -m uvo_api
cd src/uvo-gui-react && npm run dev         # React public frontend (5174 dev, 8080 prod)

# Tests
uv run pytest tests/mcp/ -v                  # unit (mocked) — run these, not `tests/`
uv run pytest tests/api/ tests/pipeline/ -v
uv run pytest tests/e2e/ -v                 # requires docker compose up
uv run pytest --cov=src -v

# Lint
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# React public GUI
cd src/uvo-gui-react && npm install && npm test
```

## Docker (local deploy)

Full stack (mcp + api + gui-react + mongo + neo4j + pipeline) lives in `docker-compose.yml`. For build/deploy/troubleshoot operations, use the `docker-troubleshoot` skill (`.claude/skills/docker-troubleshoot/`) or the `/docker` slash command. Don't reinvent — it already covers port conflicts, healthcheck debugging, mongo/neo4j volume-init gotchas, service-name URIs, and nuclear-reset tiers.

## Workflow

- New features: use `superpowers:using-git-worktrees` to create an isolated worktree before writing code. Skip for single-file fixes, docs-only edits, or changes to the in-progress branch.
- Non-trivial multi-phase work (design + build + test): prefer the `/team` skill over ad-hoc subagent spawns.

## React GUI notes

- **URL-as-state:** Pagination, filters, sort, search live in URL query params (react-router) — enables bookmarking.
- **i18n:** All Slovak strings in `src/i18n/sk.ts` only; use `t("key")` from context.
- **Utilities:** `cn()` (Tailwind class merging) from `src/lib/utils.ts`.
- **Data fetching:** TanStack Query v5, no Redux/Zustand state.
- **Graph chunk:** Cytoscape.js lazy-loaded as code-split chunk; `<Suspense>` wraps graph pages.

## Data integrity & pipeline status

**Quick health check** — per-source counts, last ingestion age, cross-source match stats:

```bash
uv run python -m uvo_pipeline health          # human-readable
uv run python -m uvo_pipeline health --json   # machine-readable
```

**What the health report shows:**

- Per source (vestnik, crz, ted, uvo, itms): total notices, ingested last 24h/7d, last ingestion timestamp
- Registry entries and skip counts (skipped = unchanged hash, not re-upserted)
- Cross-source deduplication: total canonical matches, notices linked by canonical_id
- Latest pipeline run metadata

**Mongo collections to inspect manually:**

- `notices` — canonical procurement records; unique on `(source, source_id)`
- `ingested_docs` — ingestion registry; tracks `content_hash`, `last_seen_at`, `skipped_count`
- `cross_source_matches` — cross-source deduplication results
- `pipeline_state` — checkpoint per source (last run, ITMS min_id, Vestník last_modified)
- `procurers` / `suppliers` — unique on `ico` (sparse) + `name_slug`

**Integrity invariants to verify:**

- Every notice in `notices` has a corresponding entry in `ingested_docs` with matching `content_hash`
- `(source, source_id)` is unique in `notices`; duplicates indicate a failed upsert constraint
- `ico` is unique in `procurers`/`suppliers` (sparse — nulls allowed, but non-null ICOs must be distinct)
- Notices with `canonical_id` set appear in `cross_source_matches`

**Backfill / repair scripts:**

```bash
# Backfill ITMS notices with missing procurer details
uv run python scripts/enrich_itms_procurers.py --dry-run   # preview
uv run python scripts/enrich_itms_procurers.py --limit 100 # run on first 100
```

**Cross-source deduplication** runs automatically at the end of each pipeline run (two passes: ICO+CPV match, then title-slug + date ±7 days). Re-trigger manually by running the pipeline — dedup is idempotent.

## Data / search gotchas

- Mongo uses a custom `sk_folding` analyzer (standard tokenizer + `lowercase` + `icuFolding`) for case- and diacritic-insensitive Slovak search. Name fields carry an `autocomplete` (edgeGram) subfield powering the live dropdown.
- Atlas Search indexes are created on `uvo_mcp` startup — expect a cold-start lag on a fresh Mongo volume.
- Legacy-data migration after Mongo image swap: `scripts/migrate_to_atlas_local.sh` (one-shot).
- Graph page (`/graph`) depends on Neo4j + `graph_ego_network` / `graph_cpv_network` MCP tools; if Neo4j is down the page will error, not silently degrade.

## Secrets & env

`.env` keys that matter: `MONGO_PASSWORD`, `NEO4J_PASSWORD`, `EKOSYSTEM_API_TOKEN` (optional). Inside containers, URIs must reference service names (`mongo`, `neo4j`, `mcp-server`) — never `localhost`. See the `docker-troubleshoot` skill for the full list.
