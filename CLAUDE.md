# UVO Search — Claude Context

Search and browse Slovak government procurement data. Shared MCP backend, single React frontend.

## Architecture

Five Python packages under `src/` + one React frontend:

| Package | Port | Entrypoint | Role |
| ------- | ---- | ---------- | ---- |
| `uvo_mcp` | 8000 | `uv run python -m uvo_mcp` | FastMCP server — search, detail, graph tools |
| `uvo_api` | 8001 | `uv run python -m uvo_api` | FastAPI delivery adapter; routers → `uvo_core.services` in-process; dashboard + ingestion + `/v1` |
| `uvo-gui-react` | 8080 host / 5174 dev | `cd src/uvo-gui-react && npm run dev` | React 18 SPA public frontend (Slovak UI) |
| `uvo_pipeline` | — | `uv run python -m uvo_pipeline` | Shared lib + one-shot backfill CLI (legacy; new long-lived services below) |
| `uvo_workers` | 8091–8096 | `uv run python -m uvo_workers.<service>` | Long-lived microservices (4 extractors + ingestor + dedup-worker; Redis Streams) |

**Storage:** MongoDB Atlas Local (27017, with `mongot` for Atlas Search) + Neo4j 5 with APOC (7474/7687). Both required for `uvo_mcp` to start.

**Frontend ↔ backend:** React → `uvo_api` (FastAPI) → **`uvo_core.services`** in-process (no HTTP hop). Routers call the shared query services directly; FastMCP (`uvo_mcp`) is a separate *external* delivery surface exposing the same services as LLM tools. Don't reintroduce an intra-cluster MCP HTTP call from `uvo_api`.

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
uv run pytest tests/ --ignore=tests/e2e -q  # the full unit suite (also covers tests/core, tests/gui)
uv run pytest tests/e2e/ -v                 # requires docker compose up
uv run pytest --cov=src -v

# Lint
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# React public GUI
cd src/uvo-gui-react && npm install && npm test
```

## Docker (local deploy)

> **Development only.** `docker-compose.yml` binds datastores to loopback and is not a production artifact. For production see **Production deployment** below.

`docker compose up` starts **12** services. Two are behind opt-in profiles because both exit or are dev-only, and `up --wait` counts any exited container as a failure:

```bash
docker compose --profile legacy run --rm pipeline   # ad-hoc backfill (one-shot, exits)
docker compose --profile debug up -d mongo-express  # dev-only admin UI
```

Credentials are required (`${VAR:?}`), so an empty `.env` aborts at interpolation — only `REDIS_PASSWORD` has a dev default.

Full stack lives in `docker-compose.yml` (mcp-server, api, gui-react, mongo, neo4j, redis, 4 extractors, ingestor, dedup-worker; plus profiled mongo-express and pipeline). For build/deploy/troubleshoot operations, use the `docker-troubleshoot` skill (`.claude/skills/docker-troubleshoot/`) or the `/docker` slash command. Don't reinvent — it already covers port conflicts, healthcheck debugging, mongo/neo4j/redis volume-init gotchas, service-name URIs, and nuclear-reset tiers. The `pipeline` service is now optional/legacy for ad-hoc backfills; the 6 new microservices (4 extractors + ingestor + dedup-worker) handle continuous ingestion via Redis Streams.

**Docker runs in WSL, not Docker Desktop.** All `docker compose` commands must go through WSL:

```bash
# From Windows shell (PowerShell / Git Bash), always prefix with:
MSYS_NO_PATHCONV=1 wsl -e bash -lc "cd /mnt/c/Users/User/Documents/src/uvo-search && docker compose <cmd>"

# Standard deploy cycle after code changes:
MSYS_NO_PATHCONV=1 wsl -e bash -lc "cd /mnt/c/Users/User/Documents/src/uvo-search && docker compose build api gui-react && docker compose up -d api gui-react"

# Check stack status:
MSYS_NO_PATHCONV=1 wsl -e bash -lc "cd /mnt/c/Users/User/Documents/src/uvo-search && docker compose ps"
```

Docker Desktop context (`desktop-linux`) will fail with "pipe not found" — that's expected. The WSL `docker` client uses the default context pointing to the WSL daemon.

## Workflow

- New features: use `superpowers:using-git-worktrees` to create an isolated worktree before writing code. Skip for single-file fixes, docs-only edits, or changes to the in-progress branch.
- Non-trivial multi-phase work (design + build + test): run the `feature-pipeline` workflow (`/home/max/.claude/workflows/feature-pipeline.js` via the Workflow tool) over ad-hoc subagent spawns.

## Project agents (`.claude/agents/`)

- `data-pipeline` (sonnet) — ingestion, Redis Streams workers, cross-source dedup, integrity invariants, backfills. Prefer over generic devops/developer for pipeline and data-quality work.
- `search-tuner` (opus) — Atlas Search analyzers (`sk_folding`), autocomplete, FastEmbed hybrid vector search, relevance tuning. Prefer for any search-behavior change or relevance bug.
- `procurement-domain` (opus, advisory/read-only) — Slovak procurement semantics: CPV, zákon 343/2015, vestník/CRZ/TED/ITMS meaning, IČO conventions. Use to validate features and labels against real-world semantics.
- `db-monitor` (haiku, read-only) — reports database filling: per-source counts vs. baseline, ingestion rates/ETAs, checkpoint sanity, stream lag, stalled extractors. Use to check backfill/recovery progress.

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

## CI & Docker image gotchas

- **`uv sync` must run *after* `COPY src/`.** All four Dockerfiles sync before copying sources, which resolves third-party deps only — the first-party packages never land in the venv. `uv run` used to paper over this by re-syncing at container start, but `UV_NO_SYNC=1` (needed for a read-only rootfs) disables that. Every image then builds perfectly and dies with `ModuleNotFoundError` on start. A second `uv sync --frozen --no-dev` after the COPY is what makes them work. **A build that succeeds proves nothing about whether the app starts** — CI import-checks each image for exactly this reason.
- **The E2E job is gated on `needs: [test, lint]`.** While Lint was red it was silently skipped for months, and assertions rotted behind it (`"data"` vs `"items"`, an English GUI title the Slovak UI had dropped) while two runtime-fatal image bugs shipped. It is the only check that runs the real system — keep it green, and treat a skipped E2E as a failed one.
- Prefer assertions on structure (mount points, envelope keys, bundle paths) over copy. Every stale assertion found this way was pinned to a display string.

## Data / search gotchas

- Mongo uses a custom `sk_folding` analyzer (standard tokenizer + `lowercase` + `icuFolding`) for case- and diacritic-insensitive Slovak search. Name fields carry an `autocomplete` (edgeGram) subfield powering the live dropdown.
- Atlas Search indexes are created on `uvo_mcp` startup — expect a cold-start lag on a fresh Mongo volume.
- Legacy-data migration after Mongo image swap: `scripts/migrate_to_atlas_local.sh` (one-shot).
- Graph page (`/graph`) depends on Neo4j + `graph_ego_network` / `graph_cpv_network` MCP tools; if Neo4j is down the page will error, not silently degrade.

## Production deployment — Kubernetes via ArgoCD

> **Docker Swarm is gone.** It was demolished on 2026-08-04 along with its host volumes. `docker-stack-dev.yml` and `.github/workflows/deploy-dev.yml` (`workflow_dispatch`, last ran 2026-05-11) are dead artifacts — do not use them to deploy.

Production runs on the **Hetzner k8s cluster managed from the [`stubarag-infra`](https://github.com/devopsacid/stubarag-infra) repo**, not from this one:

| Thing | Where |
| ----- | ----- |
| Helm chart | `stubarag-infra:argocd/manifests/uvo-search/` |
| ArgoCD Application | `stubarag-infra:argocd/hz/uvo-search-application.yaml` |
| Namespace | `uvo-search-dev` |
| Public host | `contract-register.agentkovac.sk` |
| Images | `ghcr.io/devopsacid/uvo-search/uvo-{mcp,api,workers,gui,pipeline}`, tag `sha-<short>` |

`argocd/hz/` is an **app-of-apps** — merging a manifest there auto-syncs to a live cluster shared with other production apps. Merging *is* deploying; treat it accordingly.

Cluster conventions (they are **not** what `deploy/k8s/` in this repo assumes):

- **Helm charts**, not kustomize
- **Longhorn** storage, not `hcloud-volumes`
- **Traefik `IngressRoute`** (CRD), not ingress-nginx or Gateway API `HTTPRoute` — HTTPRoute can't express middlewares, and the public route needs auth + security headers
- **External Secrets Operator + Vault**, not sealed-secrets
- cert-manager: **always issue against `letsencrypt-staging` first**

> `deploy/k8s/` and `deploy/argocd/` in *this* repo are superseded. They were built against the wrong conventions and were never applied to any cluster. Harvest their hardening (securityContext, PDBs, NetworkPolicies, probes, resource limits) but don't deploy from them.

## Secrets & env

**Never handle secret material directly — use the `secrets-manager` agent** for Vault paths, ESO wiring, `ghcr-pull`, GitHub Actions Secrets, and any credential generation or rotation. (`security-engineer` *reviews* secrets hygiene; `secrets-manager` *operates* on secrets.)

Production secrets live in Vault at `kv/app/uvo-search/dev` (four keys: `mongodb_password`, `neo4j_password`, `redis_password`, `api_ops_token`) and reach the cluster as the `uvo-search-secrets` Secret via an ExternalSecret. Nested under `app/` deliberately — the existing ESO policy already covers `app/*`, so no policy widening is needed.

- **An ExternalSecret fails as a whole if any one property is missing.** Omitting a key doesn't produce a partial Secret — it produces *no* Secret, and every pod that mounts it fails to start. Seed all declared keys; to disable a feature, drop the env var from the Deployment instead.
- **`vault kv put` replaces wholesale.** Never seed a shared path expecting a merge.
- Local `.env` keys: `MONGO_PASSWORD`, `NEO4J_PASSWORD`, `REDIS_PASSWORD` (optional locally — compose defaults to `uvo_redis_dev`), `EKOSYSTEM_API_TOKEN` (optional). Inside containers, URIs must use service names (`mongo`, `neo4j`, `mcp-server`) — never `localhost`.

### The `API_` prefix trap

`ApiSettings` sets `env_prefix="API_"`, so it **cannot see any unprefixed variable** — and most of its fields default to a falsy value rather than raising. The API then starts *healthy* and fails at query time, which reads as a data bug, not a config one. Three separate variables were missed this way in one migration.

Every one of these must be set explicitly, in addition to the unprefixed versions other services use: `API_MONGODB_URI`, `API_NEO4J_URI`, `API_NEO4J_USER`, `API_NEO4J_PASSWORD`, `API_REDIS_PASSWORD`. When adding a field to `ApiSettings`, prefer no default over a falsy one so a missing value fails loudly at startup.
