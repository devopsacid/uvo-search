# uvo-search Implementation Plans

Derived from the four-perspective audit of 2026-08-05 (architecture, security, code quality, deployment).

## Execution order

| Phase | Plan | Why this order |
| --- | --- | --- |
| 0 | [Test suite repair](2026-08-05-phase0-test-suite-repair.md) | 18 tests fail against a stale MCP contract, so the suite cannot catch regressions. Everything downstream needs a trustworthy suite before it changes production code. |
| 1 | [Security hardening](2026-08-05-phase1-security-hardening.md) | Deployment blockers. Independent of Phase 2 — may run in parallel with it, but must precede any public exposure. |
| 2 | [Ingestion correctness & throughput](2026-08-05-phase2-ingestion-correctness.md) | Silent data loss, invisible outages, and the two hotspots that make backfill unsafe. |
| 3 | [Kubernetes production readiness](2026-08-05-phase3-k8s-production-readiness.md) | Container and cluster hardening. Task 5 requires Phase 2 Task 1 (`/readyz`). |

## Cross-plan dependencies

- **Phase 2 Task 4** uses `redact_exception` from **Phase 1 Task 4**; a fallback is documented if Phase 1 has not merged.
- **Phase 3 Task 5** (probe repointing) requires **Phase 2 Task 1** (`/readyz` endpoint) — the plan stops the implementer if it is missing.
- **Phase 3 Task 2** (`securityContext`) requires **Phase 3 Task 1** (non-root Dockerfiles) or every pod crash-loops.

## Not yet planned

Three items are known, scoped, and deliberately deferred to their own plans:

1. **Retire the legacy `uvo_pipeline` orchestrator write path.** Two live write paths with mutually invisible checkpoints and no shared lock currently both re-fetch and re-write everything. Eliminating it removes the duplicate-write class entirely — but only once the worker path is proven correct in production.
2. **Move the MCP `TTLCache` to Redis.** This is the sole blocker on running more than one `mcp-server` replica; with N replicas today, users see different figures on refresh for up to an hour.
3. **Replace `mongodb-atlas-local` with managed Atlas or a supported operator.** A single-replica StatefulSet on one RWO PVC is the largest single point of failure in the system. Partly a commercial decision — see the open questions in `deploy/README.md`.
