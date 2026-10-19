# UVO Search — Claude Context

Search and browse Slovak government procurement data. Shared MCP backend, single React frontend.

This file describes what is live on `main`. If code and this file disagree, fix this file.

## Architecture

Five Python packages under `src/` + one React frontend:

| Package | Port | Entrypoint | Role |
| ------- | ---- | ---------- | ---- |
| `uvo_core` | — | (library) | Shared core: query services (`uvo_core.services`), domain models, infrastructure adapters (`uvo_core.adapters.{mongo,neo4j,redis}`), client factories (`uvo_core.infra.clients`). Imports none of the other packages. |
| `uvo_api` | 8001 | `uv run python -m uvo_api` | FastAPI delivery adapter: `/api/*` for the SPA (incl. `/api/analytics/*`), `/v1/*` public API, `/health`, `/readyz`, `/metrics` |
| `uvo_mcp` | 8000 | `uv run python -m uvo_mcp` (`stdio` arg for stdio transport) | FastMCP server — external LLM tool surface over the same services |
| `uvo_workers` | 8091–8096 | `uv run python -m uvo_workers.<service>` | Long-lived services: 4 extractors (`vestnik`, `crz`, `ted`, `itms`), `ingestor`, `dedup-worker`; Redis Streams |
| `uvo_pipeline` | — | `uv run python -m uvo_pipeline [health]` | Source extractors and transformers (shared with the workers), `health` CLI, legacy one-shot backfill orchestrator |
| `uvo-gui-react` | 8080 host / 5174 dev | `cd src/uvo-gui-react && npm run dev` | React 18 SPA public frontend (Slovak UI) |

**Storage:** MongoDB Atlas Local (27017, with `mongot` for Atlas Search), Neo4j 5 with APOC (7474/7687), Redis 7 (streams, pub/sub, locks, ITMS cache). MCP starts without Mongo/Neo4j, but DB-backed tools return 503 and `/readyz` stays 503.

**Frontend ↔ backend:** React → `uvo_api` (FastAPI) → **`uvo_core.services`** in-process (no HTTP hop). Routers call the typed service functions directly; there is no string dispatcher. Backend outages raise `uvo_core.errors.BackendUnavailable`, which one exception handler in `uvo_api` maps to 503. Clients are created in the app lifespan and owned there. FastMCP (`uvo_mcp`) is a separate *external* delivery surface exposing the same services as LLM tools. Don't reintroduce an intra-cluster MCP HTTP call from `uvo_api`.

**Layering:** `uvo_core` imports none of the other packages. `uvo_core` and `uvo_pipeline` never import the entrypoint packages (`uvo_api`, `uvo_mcp`, `uvo_workers`), and the entrypoints don't import each other. CI enforces this with import-linter (`uv run lint-imports`; contracts in `pyproject.toml`).

**Health:** `/health` is liveness only and never checks dependencies. `/readyz` on API and MCP does a bounded Mongo ping and checks that the required Atlas Search indexes exist; it returns 503 otherwise. Workers serve JSON snapshots on `/health` at their ports above. Prometheus `/metrics` is served by API, MCP and every worker port, outside `/api` so nginx never proxies it. API `/metrics` labels HTTP metrics by route template only.

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
monitoring/scripts/validate.sh              # promtool + dashboard JSON checks (needs docker, jq)

# Lint (CI runs all three)
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run lint-imports

# React public GUI (CI runs lint, tsc, vitest and build)
cd src/uvo-gui-react && npm ci && npm run lint && npx tsc -b && npm test -- --run && npm run build
```

## Docker (local deploy)

> **Development only.** `docker-compose.yml` binds datastores to loopback and is not a production artifact. For production see **Production deployment** below.

**Images:** one multi-stage root `Dockerfile` builds every Python image; pick one with `--target mcp | api | workers | pipeline`. The GUI image is `src/uvo-gui-react/Dockerfile`. `docker-compose.yml` sets the targets.

`docker compose up` starts **12** services: mcp-server, api, gui-react, mongo, neo4j, redis, the 4 extractors, ingestor and dedup-worker. Two are behind opt-in profiles because both exit or are dev-only, and `up --wait` counts any exited container as a failure:

```bash
docker compose --profile legacy run --rm pipeline   # ad-hoc backfill (one-shot, exits)
docker compose --profile debug up -d mongo-express  # dev-only admin UI
docker compose --profile monitoring up -d           # Prometheus 127.0.0.1:9090, Grafana 127.0.0.1:3000
```

The `monitoring` profile is opt-in and not part of the 12. Its rules and dashboards live as code in `monitoring/` (`monitoring/README.md` has the logins and alert runbook). Grafana's admin password comes from `GRAFANA_ADMIN_PASSWORD`; the dev default `uvo_grafana_dev` is acceptable only because the port is loopback-bound.

Credentials are required (`${VAR:?}`), so an empty `.env` aborts at interpolation — only `REDIS_PASSWORD` has a dev default.

Full stack lives in `docker-compose.yml`. For build/deploy/troubleshoot operations, use the `docker-troubleshoot` skill (`.claude/skills/docker-troubleshoot/`) or the `/docker` slash command. Don't reinvent — it already covers port conflicts, healthcheck debugging, mongo/neo4j/redis volume-init gotchas, service-name URIs, and nuclear-reset tiers. The `pipeline` service is optional/legacy for ad-hoc backfills; the 6 microservices (4 extractors + ingestor + dedup-worker) handle continuous ingestion via Redis Streams.

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

- **API paths:** all SPA REST routes live under `/api/...` (for example `/api/contracts`, `/api/graph/ego/{ico}`); the public API is under `/v1/...`.
- **URL-as-state:** Pagination, filters, sort, search live in URL query params (react-router) — enables bookmarking.
- **i18n:** All Slovak strings in `src/i18n/sk.ts` only; use `t("key")` from context.
- **Utilities:** `cn()` (Tailwind class merging) from `src/lib/utils.ts`.
- **Data fetching:** TanStack Query v5 (query client factory in `src/api/queryClient.ts`), no Redux/Zustand state.
- **Graph chunk:** Cytoscape.js lazy-loaded as code-split chunk; `<Suspense>` wraps graph pages.
- **Analytics dashboards:** `/analytika/{prehlad,koncentracia,cpv,pokrytie}` (`/` → `prehlad`, `/cpv-trends` → `cpv`). Filters `date_from`, `date_to`, `cpv`, `source`, `procurer_ico`, `supplier_ico` (+ `dimension` on koncentracia) are URL params; `/zakazky` accepts the same names as drill-down targets. Backend: `/api/analytics/*` (`routers/analytics.py`, `uvo_core/services/analytics.py`). CSV export goes through `src/lib/csv.ts` (BOM, `;`, decimal comma).
- **Metric definition D1** (all dashboards, spec §4): one `contract_award` notice = one contract; value = `final_value` → `estimated_value` → 0; date = `award_date` → `publication_date`; supplier attribution by distinct award ICO. Entity-list sorting and the Firma "Prehľad" KPIs still use the entity-doc definition (all notice types), so totals can differ from a dashboard filtered to the same ICO (F2, still open).

## Workers (`uvo_workers`)

- **Shared scaffolding:** `WorkerContext` owns the process's Mongo/Redis/Neo4j handles, built by `uvo_workers/clients.py` (`WorkerClients`). The four extractors are declared as `SourceSpec`s and run through one generic loop, `run_extract` (`uvo_workers/extract.py`). Settings derive from `WorkerSettings`; env var names are the field names, with no prefix.
- **Ingestor reliability** (`uvo_workers/ingestor.py`):
  - An entry is acked only after its notice is written to both Mongo and Neo4j. Failed entries stay pending.
  - Pending entries are reclaimed on a timer (`INGESTOR_RECLAIM_INTERVAL_SECONDS`, cursor-paged XAUTOCLAIM), whether or not new traffic is flowing.
  - After `INGESTOR_MAX_DELIVERIES` an entry is processed alone. If it still fails, it is copied to `notices:dead` and acked. If every over-limit entry fails in the same batch, that looks like an outage, so they stay pending instead of being dead-lettered.
  - **Producer backpressure:** extractors pause while consumer-group lag + pending ≥ `STREAM_HIGH_WATER`, and fail the cycle after 15 minutes.
  - **Trimming:** `XTRIM MINID` removes only fully acked entries. `STREAM_MAXLEN_APPROX` is a memory safety net, not the retention mechanism.
- **Dead letters:** watch `XLEN notices:dead` and the `uvo_worker_dead_letter_length` metric. The `health` CLI and the `db-monitor` agent do not read `notices:dead` yet.
- **Metrics:** `uvo_workers/metrics.py` serves the `uvo_worker_*` families on each worker's `/metrics`. Counters that come from the snapshot (`cycles_completed`, `dedup_runs`, …) are emitted only when the worker tracks them, so an extractor never reports `dedup_runs`. Alerts and dashboards depend on these names (`monitoring/prometheus/rules/uvo-alerts.yml`).

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

**Redis streams:** `notices:{vestnik,crz,ted,itms}` (ingest queues, consumer group `ingestor`), `notices:dead` (dead letters), `notices:written` (pub/sub, triggers dedup and cache invalidation).

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

**Cross-source deduplication** runs in the `dedup-worker`: debounced on `notices:written`, with an hourly fallback poll, guarded by the `dedup:lock` Redis lock. Two passes: ICO+CPV match, then title-slug + date ±7 days. It is idempotent.

## CI & Docker image gotchas

- **Pipeline (`.github/workflows/ci.yml`):** `test` (unit tests), `lint` (ruff + `lint-imports`), `frontend` (eslint, `tsc -b`, vitest, build), `images` (builds each image and imports its first-party packages on a read-only rootfs; nginx check for the GUI), `manifests` (kubeconform on `deploy/k8s`), and `docker-compose` (compose up + E2E).
- **The E2E job needs `test`, `lint` and `frontend`.** While Lint was red it was silently skipped for months, and assertions rotted behind it (`"data"` vs `"items"`, an English GUI title the Slovak UI had dropped) while two runtime-fatal image bugs shipped. It is the only check that runs the real system — keep it green, and treat a skipped E2E as a failed one.
- **Monitoring job (`monitoring`):** runs `monitoring/scripts/validate.sh` (promtool config/rules/rule tests, dashboard JSON checks), then starts only Prometheus and Grafana to confirm the dashboards provision. It is not in the E2E job's `needs`, so it does not gate E2E.
- **Publishing (`docker-publish.yml`)** runs via `workflow_run`, and only after CI succeeds on a `push` to `main`. It builds the exact commit CI validated and pushes `ghcr.io/<repo>/uvo-{mcp,api,workers,gui,pipeline}` with tags `sha-<7-char>` and `latest`. Prod pins the `sha-` tag. Publishing never deploys, and the tag names are consumed downstream, so don't rename them.
- **`uv sync` must run *after* `COPY src/`.** Each target stage in the root `Dockerfile` syncs third-party deps once in a shared `deps` stage, then copies only its own packages and runs `uv sync --frozen --no-dev` again. Without that second sync, the first-party packages never reach the venv and the container dies with `ModuleNotFoundError` on start. Runtime stages contain no `uv` binary; commands run `python -m …` straight from `/app/.venv` on PATH. **A build that succeeds proves nothing about whether the app starts** — that is why CI import-checks each image.
- **fastembed model** is baked into the `mcp` image at `/opt/fastembed` (`FASTEMBED_CACHE_PATH`). Keep it outside `/tmp`: k8s mounts an emptyDir over `/tmp`, which would hide it.
- Prefer assertions on structure (mount points, envelope keys, bundle paths) over copy. Every stale assertion found this way was pinned to a display string.

## Data / search gotchas

- Mongo uses a custom `sk_folding` analyzer (standard tokenizer + `lowercase` + `icuFolding`) for case- and diacritic-insensitive Slovak search. Name fields carry an `autocomplete` (edgeGram) subfield powering the live dropdown.
- Atlas Search indexes are created idempotently on `uvo_mcp` and `uvo_api` startup (`uvo_core.adapters.mongo.search_indexes`) — expect a cold-start lag on a fresh Mongo volume; both `/readyz` endpoints stay 503 until the required indexes exist. Failures are logged at ERROR. A drifted index definition is updated in place, which triggers an async rebuild: text search is empty or degraded until the index is READY again.
- Legacy-data migration after Mongo image swap: `scripts/migrate_to_atlas_local.sh` (one-shot).
- Analytics aggregates run at query time over `notices` (no precomputed stats), with `maxTimeMS` 15 s and 15-min caches. The ingestor creates the B-tree indexes they need (`notice_type_award_date_desc`, `source_notice_type_publication_date_desc`). Measure cold cost with `MONGODB_URI=... uv run python scripts/bench_analytics.py` before changing a default range. `/api/contracts?source=` filters on the `$search` path after the search stage, so the Atlas index mapping does not change.
- Graph endpoints (`/api/graph/*`) and the MCP graph tools need Neo4j. If Neo4j is down or unset, they return an error or 503; they do not silently degrade.

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
- **Probes:** liveness `/health`, readiness `/readyz` on both API and MCP.
- **MCP Redis env:** MCP reads unprefixed `REDIS_URL` and `REDIS_PASSWORD` for the `notices:written` cache-invalidation subscriber. Without them it falls back to TTL-only caching and logs a warning. The stubarag-infra chart must pass both.

> `deploy/k8s/` and `deploy/argocd/` in *this* repo are superseded. They were built against the wrong conventions and were never applied to any cluster. Harvest their hardening (securityContext, PDBs, NetworkPolicies, probes, resource limits) but don't deploy from them.

## Secrets & env

**Never handle secret material directly — use the `secrets-manager` agent** for Vault paths, ESO wiring, `ghcr-pull`, GitHub Actions Secrets, and any credential generation or rotation. (`security-engineer` *reviews* secrets hygiene; `secrets-manager` *operates* on secrets.)

Production secrets live in Vault at `kv/app/uvo-search/dev` (four keys: `mongodb_password`, `neo4j_password`, `redis_password`, `api_ops_token`) and reach the cluster as the `uvo-search-secrets` Secret via an ExternalSecret. Nested under `app/` deliberately — the existing ESO policy already covers `app/*`, so no policy widening is needed.

- **An ExternalSecret fails as a whole if any one property is missing.** Omitting a key doesn't produce a partial Secret — it produces *no* Secret, and every pod that mounts it fails to start. Seed all declared keys; to disable a feature, drop the env var from the Deployment instead.
- **`vault kv put` replaces wholesale.** Never seed a shared path expecting a merge.
- Local `.env` keys: `MONGO_PASSWORD`, `NEO4J_PASSWORD`, `REDIS_PASSWORD` (optional locally — compose defaults to `uvo_redis_dev`), `EKOSYSTEM_API_TOKEN` (optional). Inside containers, URIs must use service names (`mongo`, `neo4j`, `mcp-server`) — never `localhost`.

### The `API_` prefix trap

`ApiSettings` sets `env_prefix="API_"`, so it **cannot see any unprefixed variable**. `API_MONGODB_URI` has no default and fails startup when missing, which is intended. Most other `API_*` fields do have defaults, and a missing one fails late instead: an unset `API_NEO4J_URI` turns graph endpoints into 503s, and a missing `API_REDIS_PASSWORD` makes the `/v1` rate limiter fail closed on every request. Set these explicitly, in addition to the unprefixed versions other services use: `API_MONGODB_URI`, `API_NEO4J_URI`, `API_NEO4J_USER`, `API_NEO4J_PASSWORD`, `API_REDIS_PASSWORD`. When adding a field to `ApiSettings`, prefer no default over a falsy one so a missing value fails loudly at startup.
