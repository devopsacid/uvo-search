# Phase 3 — Kubernetes Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the existing `deploy/k8s/` manifests from "renders cleanly" to "safe to run unattended on a public Hetzner cluster" — non-root containers, real probes, network isolation, reproducible images, and metrics that make alerting possible.

**Architecture:** The manifests already have the right topology (ClusterIP datastores, no ingress to MCP, secrets templated for sealed-secrets). What they lack is the hardening layer. Containers run as root because no Dockerfile declares a `USER`, so the image change must land before the `securityContext` that assumes it. Probes are wired to an endpoint that always returned 200 until Phase 2 added `/readyz`. Everything here is additive — base manifests gain fields, the Hetzner overlay gains patches.

**Tech Stack:** Docker, Kustomize v5, Kubernetes, ingress-nginx, cert-manager, prometheus-client, kubeconform, GitHub Actions, ArgoCD.

## Global Constraints

- **Prerequisite:** Phase 2 Task 1 must be merged — the probe changes in Task 5 target `/readyz`, which does not exist before then.
- Every task that touches YAML ends with `kubectl kustomize deploy/k8s/overlays/hetzner > /dev/null` exiting 0.
- Never apply anything to a live cluster in this plan. Rendering and validating only. Deployment is a separate, human-gated step.
- No real secrets in any tracked file.
- Conventional Commits.
- Keep base manifests environment-agnostic; anything Hetzner-specific belongs in `overlays/hetzner/`.

---

### Task 1: Run containers as a non-root user

**Files:**
- Modify: `Dockerfile.mcp`, `Dockerfile.api`, `Dockerfile.workers`, `Dockerfile.pipeline`
- Test: `tests/test_dockerfiles.py` (create)

No Dockerfile declares a `USER`, so every Python service runs as uid 0. This must land before Task 2, which adds a `securityContext` that would otherwise crash-loop every pod.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dockerfiles.py`:

```python
"""Every application image must declare a non-root USER.

Root-in-container removes the last containment layer: a container escape via
a runtime or kernel CVE lands as root on the Hetzner node.
"""

from pathlib import Path

import pytest

DOCKERFILES = [
    "Dockerfile.mcp",
    "Dockerfile.api",
    "Dockerfile.workers",
    "Dockerfile.pipeline",
]


@pytest.mark.parametrize("name", DOCKERFILES)
def test_declares_non_root_user(name):
    content = Path(name).read_text(encoding="utf-8")
    user_lines = [ln.strip() for ln in content.splitlines() if ln.strip().startswith("USER ")]
    assert user_lines, f"{name} does not declare a USER; it runs as root"
    final_user = user_lines[-1].split(None, 1)[1].strip()
    assert final_user not in ("root", "0"), f"{name} ends as root"


@pytest.mark.parametrize("name", DOCKERFILES)
def test_user_is_last_privileged_step(name):
    """USER must come after package installs, or the build fails on permissions."""
    content = Path(name).read_text(encoding="utf-8")
    lines = [ln.strip() for ln in content.splitlines()]
    user_idx = max(i for i, ln in enumerate(lines) if ln.startswith("USER "))
    installs = [i for i, ln in enumerate(lines) if "uv sync" in ln or "apt-get install" in ln]
    assert all(i < user_idx for i in installs), f"{name} installs packages after dropping privileges"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_dockerfiles.py -v`
Expected: FAIL — all four report no `USER` declared.

- [ ] **Step 3: Inspect one Dockerfile to learn the existing layout**

Run: `cat -n Dockerfile.api`
Expected: shows the base image, `uv sync`, the `COPY` of `src/`, and the `CMD`/`ENTRYPOINT`. Note where the working directory is set and whether anything writes to disk at runtime (e.g. `/app/cache`).

- [ ] **Step 4: Add a non-root user to each Dockerfile**

In **each** of the four files, insert immediately before the final `CMD`/`ENTRYPOINT` line — after every `RUN`, `COPY`, and `uv sync`:

```dockerfile
# Run as an unprivileged user. uid is fixed so the k8s securityContext can
# assert runAsUser without depending on image internals.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && chown -R 10001:10001 /app
USER 10001
```

If the image is Alpine-based (check the `FROM` line), use the busybox equivalent instead:

```dockerfile
RUN adduser -u 10001 -D -s /sbin/nologin app && chown -R 10001:10001 /app
USER 10001
```

For `Dockerfile.workers` and `Dockerfile.pipeline`, which use `/app/cache` at runtime, ensure the directory exists and is owned before the `USER` line:

```dockerfile
RUN mkdir -p /app/cache && chown -R 10001:10001 /app/cache
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_dockerfiles.py -v`
Expected: 8 passed.

- [ ] **Step 6: Verify one image actually builds and runs as uid 10001**

Run: `docker build -f Dockerfile.api -t uvo-api:nonroot-check . && docker run --rm --entrypoint id uvo-api:nonroot-check`
Expected: build succeeds; `id` prints `uid=10001`. If the build fails on a permission error, the `chown` is missing a path the build writes to — add it rather than moving `USER` earlier.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile.mcp Dockerfile.api Dockerfile.workers Dockerfile.pipeline tests/test_dockerfiles.py
git commit -m "fix(docker): run all application images as non-root uid 10001"
```

---

### Task 2: Add pod and container security contexts

**Files:**
- Create: `deploy/k8s/base/security-context-patch.yaml`
- Modify: `deploy/k8s/base/kustomization.yaml`

Rather than editing nine Deployments and three StatefulSets by hand, apply one patch to every workload via a kustomize target selector.

- [ ] **Step 1: Confirm the workload names the patch must cover**

Run: `kubectl kustomize deploy/k8s/overlays/hetzner | grep -E "^kind:|^  name:" | paste - - | grep -E "Deployment|StatefulSet"`
Expected: lists 9 Deployments and 3 StatefulSets. Record them — Step 4 verifies the patch reached all of them.

- [ ] **Step 2: Write the security context patch**

Create `deploy/k8s/base/security-context-patch.yaml`:

```yaml
# Applied to every Deployment via kustomize patches.target. StatefulSets are
# excluded: the mongo/neo4j/redis upstream images manage their own uid and
# write to their data volumes, so forcing runAsUser breaks them.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: PATCH_TARGET
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: PATCH_CONTAINER
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
```

- [ ] **Step 3: Wire the patch to all Deployments**

In `deploy/k8s/base/kustomization.yaml`, append:

```yaml
patches:
  - path: security-context-patch.yaml
    target:
      kind: Deployment
```

Kustomize matches the patch to each target by kind, ignoring the placeholder `metadata.name`. The container-level block requires the container name to match; if your Deployments use differing container names, drop the `containers:` section from the patch and instead add the container `securityContext` inline to each Deployment in `api.yaml`, `mcp-server.yaml`, `gui-react.yaml`, and `workers.yaml`.

- [ ] **Step 4: Verify the patch reached every Deployment**

Run: `kubectl kustomize deploy/k8s/overlays/hetzner | grep -c "runAsNonRoot: true"`
Expected: `9` — one per Deployment. If lower, the patch target is not matching; check the `target:` selector.

- [ ] **Step 5: Give read-only-root containers a writable temp dir**

`readOnlyRootFilesystem: true` breaks anything writing to `/tmp`. Add an `emptyDir` to each Deployment that needs it — at minimum `gui-react` (nginx writes cache and pid files) and the workers (which use `/app/cache`). In `gui-react.yaml`:

```yaml
          volumeMounts:
            - name: nginx-tmp
              mountPath: /tmp
            - name: nginx-cache
              mountPath: /var/cache/nginx
            - name: nginx-run
              mountPath: /var/run
      volumes:
        - name: nginx-tmp
          emptyDir: {}
        - name: nginx-cache
          emptyDir: {}
        - name: nginx-run
          emptyDir: {}
```

Merge these into the existing `volumeMounts`/`volumes` lists rather than replacing them.

- [ ] **Step 6: Verify the manifests still render**

Run: `kubectl kustomize deploy/k8s/overlays/hetzner > /dev/null && echo RENDER_OK`
Expected: `RENDER_OK`.

- [ ] **Step 7: Commit**

```bash
git add deploy/k8s/base/security-context-patch.yaml deploy/k8s/base/kustomization.yaml deploy/k8s/base/gui-react.yaml
git commit -m "feat(k8s): drop all capabilities, enforce non-root and read-only rootfs on all Deployments"
```

---

### Task 3: Graceful termination and disruption budgets

**Files:**
- Create: `deploy/k8s/base/pdb.yaml`
- Modify: `deploy/k8s/base/workers.yaml`, `api.yaml`, `mcp-server.yaml`, `gui-react.yaml`
- Modify: `deploy/k8s/base/kustomization.yaml`

The default 30-second grace period is too short for the ingestor: `read_group` blocks 5 seconds and a batch write can exceed the remainder, so SIGKILL lands mid-batch. Nothing declares a PDB, so a node drain can take down the sole ingestor and api replica at once.

- [ ] **Step 1: Set explicit grace periods**

In `deploy/k8s/base/workers.yaml`, add to **each** of the six worker Deployment pod specs, as a sibling of `containers:`:

```yaml
      # read_group blocks 5s and a batch write can take longer; the default 30s
      # risks SIGKILL mid-batch, which strands entries in the PEL.
      terminationGracePeriodSeconds: 60
```

Add the same field (value `30` is fine for the stateless tier) to the pod specs in `api.yaml`, `mcp-server.yaml`, and `gui-react.yaml`.

- [ ] **Step 2: Write the PodDisruptionBudgets**

Create `deploy/k8s/base/pdb.yaml`:

```yaml
# Keeps a voluntary disruption (node drain, cluster upgrade) from removing the
# only replica of a service. Uses maxUnavailable rather than minAvailable so a
# single-replica Deployment is not permanently undrainable.
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: uvo-api
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: api
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: uvo-gui-react
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: gui-react
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: uvo-mcp-server
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: mcp-server
```

Confirm the label keys match what the Deployments actually set — run `kubectl kustomize deploy/k8s/overlays/hetzner | grep -A3 "matchLabels"` and use the real key (it may be `app.kubernetes.io/name` rather than `app`).

- [ ] **Step 3: Register the new file**

Add `- pdb.yaml` to the `resources:` list in `deploy/k8s/base/kustomization.yaml`.

- [ ] **Step 4: Verify rendering and count**

Run: `kubectl kustomize deploy/k8s/overlays/hetzner | grep -c "kind: PodDisruptionBudget"`
Expected: `3`.

Run: `kubectl kustomize deploy/k8s/overlays/hetzner | grep -c "terminationGracePeriodSeconds"`
Expected: `9`.

- [ ] **Step 5: Commit**

```bash
git add deploy/k8s/base/pdb.yaml deploy/k8s/base/kustomization.yaml deploy/k8s/base/workers.yaml deploy/k8s/base/api.yaml deploy/k8s/base/mcp-server.yaml deploy/k8s/base/gui-react.yaml
git commit -m "feat(k8s): add PodDisruptionBudgets and explicit termination grace periods"
```

---

### Task 4: Restrict pod-to-pod traffic with NetworkPolicies

**Files:**
- Create: `deploy/k8s/base/networkpolicy.yaml`
- Modify: `deploy/k8s/base/kustomization.yaml`

The pod network is flat: any compromised pod can reach Mongo, Neo4j, and Redis directly, and can call the MCP server bypassing every constraint the API enforces.

- [ ] **Step 1: Confirm the CNI enforces NetworkPolicy**

Run: `kubectl get pods -A -o name 2>/dev/null | grep -Ei "cilium|calico|weave" || echo "CHECK_MANUALLY"`
Expected: names a policy-capable CNI. If it prints `CHECK_MANUALLY` or you have no cluster access, still add the policies — they are inert under a CNI that ignores them — but note in `deploy/README.md` that enforcement must be verified before relying on them.

- [ ] **Step 2: Write the policies**

Create `deploy/k8s/base/networkpolicy.yaml`:

```yaml
# Default deny-all ingress in the namespace; each policy below re-opens
# exactly one path. Egress is left unrestricted so workers can reach the
# upstream government APIs.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
spec:
  podSelector: {}
  policyTypes: ["Ingress"]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-to-gui
spec:
  podSelector:
    matchLabels:
      app: gui-react
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8080
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-gui-and-ingress-to-api
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: gui-react
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8001
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-to-mcp
spec:
  podSelector:
    matchLabels:
      app: mcp-server
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 8000
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-datastore-access
spec:
  podSelector:
    matchExpressions:
      - key: app
        operator: In
        values: ["mongo", "neo4j", "redis"]
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector:
            matchExpressions:
              - key: app
                operator: In
                values:
                  - api
                  - mcp-server
                  - ingestor
                  - dedup-worker
                  - extractor-vestnik
                  - extractor-crz
                  - extractor-ted
                  - extractor-itms
```

Substitute the real label key and values confirmed in Task 3 Step 2 — if the Deployments label pods `app.kubernetes.io/name: api`, every selector above must use that key.

- [ ] **Step 3: Register the file and verify rendering**

Add `- networkpolicy.yaml` to `resources:` in `deploy/k8s/base/kustomization.yaml`, then run:

`kubectl kustomize deploy/k8s/overlays/hetzner | grep -c "kind: NetworkPolicy"`
Expected: `5`.

- [ ] **Step 4: Document the ingress-namespace label prerequisite**

The `gui-react` and `api` policies match `kubernetes.io/metadata.name: ingress-nginx`. That label is automatic on Kubernetes 1.21+. Add a line to `deploy/README.md` under prerequisites:

> NetworkPolicies assume the ingress controller runs in a namespace named `ingress-nginx` and that the CNI enforces NetworkPolicy. Verify both before relying on network isolation.

- [ ] **Step 5: Commit**

```bash
git add deploy/k8s/base/networkpolicy.yaml deploy/k8s/base/kustomization.yaml deploy/README.md
git commit -m "feat(k8s): default-deny ingress with explicit allow paths for gui, api, mcp, datastores"
```

---

### Task 5: Point probes at the real readiness endpoint

**Files:**
- Modify: `deploy/k8s/base/workers.yaml` (12 probe blocks)

**Depends on:** Phase 2 Task 1 (`/readyz` must exist).

Readiness and liveness currently use an identical `httpGet /health` differing only in `initialDelaySeconds`. Since Phase 2, `/healthz` is the correct liveness target (always 200 while the process lives) and `/readyz` the correct readiness target (503 when Redis is down or the last cycle errored).

- [ ] **Step 1: Confirm the new endpoints exist in the application**

Run: `grep -n "_READY_PATHS\|readyz" src/uvo_workers/health.py`
Expected: shows `/readyz` handled. If absent, STOP — complete Phase 2 Task 1 first.

- [ ] **Step 2: Repoint every readiness probe**

In `deploy/k8s/base/workers.yaml`, change **every** `readinessProbe` `httpGet.path` from `/health` to `/readyz`, and every `livenessProbe` `httpGet.path` to `/healthz`. A worker probe pair ends up as:

```yaml
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8095
            initialDelaySeconds: 15
            periodSeconds: 20
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8095
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 2
```

Keep each container's existing port — the six workers use 8091–8096, not one shared port.

- [ ] **Step 3: Verify every probe was repointed**

Run: `kubectl kustomize deploy/k8s/overlays/hetzner | grep -c "path: /readyz"`
Expected: `6` — one per worker Deployment.

Run: `kubectl kustomize deploy/k8s/overlays/hetzner | grep -c "path: /health$"`
Expected: `0` — no probe still targets the always-200 path.

- [ ] **Step 4: Commit**

```bash
git add deploy/k8s/base/workers.yaml
git commit -m "fix(k8s): split worker liveness (/healthz) from readiness (/readyz)"
```

---

### Task 6: Pin images to immutable tags

**Files:**
- Modify: `deploy/k8s/overlays/hetzner/kustomization.yaml`
- Modify: `.github/workflows/docker-publish.yml`

`newTag: latest` makes rollouts non-reproducible, defeats `kubectl rollout undo`, and breaks ArgoCD drift detection — the desired state never changes even when the running image does.

- [ ] **Step 1: Check what tags the publish workflow already emits**

Run: `grep -n "tags:\|type=sha\|type=ref" .github/workflows/docker-publish.yml`
Expected: shows `type=sha,format=short` among the metadata-action tag rules. If absent, add it to the `tags:` list of the `docker/metadata-action` step:

```yaml
          tags: |
            type=sha,format=short
            type=ref,event=branch
```

- [ ] **Step 2: Replace `latest` with a pinned tag in the overlay**

In `deploy/k8s/overlays/hetzner/kustomization.yaml`, change the `images:` block so each entry carries an explicit immutable tag:

```yaml
# Tag is the short commit SHA emitted by .github/workflows/docker-publish.yml.
# CI updates these four lines on release; ArgoCD then sees a real desired-state
# change. Never use `latest` — it makes rollback and drift detection meaningless.
images:
  - name: REGISTRY_PLACEHOLDER/uvo-mcp
    newTag: sha-0000000
  - name: REGISTRY_PLACEHOLDER/uvo-api
    newTag: sha-0000000
  - name: REGISTRY_PLACEHOLDER/uvo-workers
    newTag: sha-0000000
  - name: REGISTRY_PLACEHOLDER/uvo-gui-react
    newTag: sha-0000000
```

Preserve the exact image names already present in the file — run `grep -n "name:" deploy/k8s/overlays/hetzner/kustomization.yaml` first and keep them.

- [ ] **Step 3: Verify no `latest` survives in the render**

Run: `kubectl kustomize deploy/k8s/overlays/hetzner | grep -n "image:.*latest"`
Expected: no output for application images. Third-party StatefulSet images (`mongodb-atlas-local`, `mongo-express`) are addressed in Step 4.

- [ ] **Step 4: Pin the third-party images**

In `deploy/k8s/base/mongo.yaml`, `neo4j.yaml`, and `redis.yaml`, replace mutable tags with digest pins. Obtain each digest:

```bash
docker buildx imagetools inspect mongodb/mongodb-atlas-local:8.0 --format '{{.Manifest.Digest}}'
docker buildx imagetools inspect neo4j:5.26 --format '{{.Manifest.Digest}}'
docker buildx imagetools inspect redis:7-alpine --format '{{.Manifest.Digest}}'
```

Then set each `image:` to `repo:tag@sha256:<digest>` using the values printed. Pin a concrete minor version rather than a floating major (`neo4j:5.26`, not `neo4j:5`).

- [ ] **Step 5: Verify rendering and commit**

Run: `kubectl kustomize deploy/k8s/overlays/hetzner > /dev/null && echo RENDER_OK`
Expected: `RENDER_OK`.

```bash
git add deploy/k8s/overlays/hetzner/kustomization.yaml deploy/k8s/base/mongo.yaml deploy/k8s/base/neo4j.yaml deploy/k8s/base/redis.yaml .github/workflows/docker-publish.yml
git commit -m "fix(k8s): pin application images to commit SHAs and third-party images to digests"
```

---

### Task 7: Expose Prometheus metrics from the workers

**Files:**
- Modify: `pyproject.toml` (add `prometheus-client`)
- Create: `src/uvo_workers/metrics.py`
- Modify: `src/uvo_workers/health.py` (serve `/metrics`)
- Test: `tests/workers/test_metrics.py` (create)

Today's observability is per-process dict counters that reset on restart, served by a hand-rolled HTTP server that nothing scrapes. Without metrics there is no alerting and no HPA — Redis stream lag is the signal that would drive ingestor scaling.

- [ ] **Step 1: Add the dependency**

Run: `uv add prometheus-client`
Expected: `pyproject.toml` gains the dependency and `uv.lock` updates.

- [ ] **Step 2: Write the failing test**

Create `tests/workers/test_metrics.py`:

```python
"""Workers expose Prometheus metrics for alerting and autoscaling."""

from uvo_workers.metrics import build_registry, render_metrics


def test_renders_counter_values_from_snapshot():
    registry = build_registry("ingestor")
    payload = render_metrics(registry, {"batches_processed": 7, "notices_written": 300})
    text = payload.decode()
    assert "uvo_worker_batches_processed_total" in text
    assert "7.0" in text


def test_readiness_is_exposed_as_a_gauge():
    registry = build_registry("ingestor")
    payload = render_metrics(registry, {"redis_connected": False, "last_error": "boom"})
    assert "uvo_worker_redis_connected 0.0" in payload.decode()


def test_unknown_snapshot_keys_are_ignored():
    registry = build_registry("ingestor")
    render_metrics(registry, {"something_new": 1, "batches_processed": 2})
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/workers/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'uvo_workers.metrics'`.

- [ ] **Step 4: Write the implementation**

Create `src/uvo_workers/metrics.py`:

```python
"""Prometheus metrics rendering for worker health endpoints."""

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest


def build_registry(component: str) -> CollectorRegistry:
    """Create a registry with the standard worker metric family.

    A fresh registry per process keeps the workers independent and avoids the
    global default registry, which makes tests order-dependent.
    """
    registry = CollectorRegistry()
    registry._uvo = {  # noqa: SLF001 - deliberate handle for render_metrics
        "batches": Counter(
            "uvo_worker_batches_processed",
            "Batches processed since start",
            ["component"],
            registry=registry,
        ),
        "notices": Counter(
            "uvo_worker_notices_written",
            "Notices written since start",
            ["component"],
            registry=registry,
        ),
        "redis": Gauge(
            "uvo_worker_redis_connected",
            "1 when the Redis connection is healthy",
            registry=registry,
        ),
        "component": component,
    }
    return registry


def render_metrics(registry: CollectorRegistry, snapshot: dict) -> bytes:
    """Project a worker metrics dict onto the registry and render it."""
    handles = registry._uvo  # noqa: SLF001
    component = handles["component"]

    batches = snapshot.get("batches_processed")
    if batches is not None:
        current = handles["batches"].labels(component=component)._value.get()  # noqa: SLF001
        handles["batches"].labels(component=component).inc(max(0, batches - current))

    notices = snapshot.get("notices_written")
    if notices is not None:
        current = handles["notices"].labels(component=component)._value.get()  # noqa: SLF001
        handles["notices"].labels(component=component).inc(max(0, notices - current))

    handles["redis"].set(1 if snapshot.get("redis_connected") else 0)
    return generate_latest(registry)
```

- [ ] **Step 5: Serve `/metrics` from the health server**

In `src/uvo_workers/health.py`, extend `serve_health` to accept an optional registry and handle the path:

```python
from prometheus_client import CollectorRegistry

from uvo_workers.metrics import render_metrics
```

Add the keyword-only parameter `registry: CollectorRegistry | None = None` to `serve_health`, and inside `handle`, before the readiness branch:

```python
            if path == "/metrics" and registry is not None:
                body = render_metrics(registry, metrics)
                writer.write(b"HTTP/1.1 200 OK\r\n")
                writer.write(b"Content-Type: text/plain; version=0.0.4\r\n")
                writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode())
                writer.write(body)
                await writer.drain()
                return
```

Then pass a registry at each call site — in `ingestor.py`:

```python
    metrics_registry = build_registry("ingestor")
    health_task = asyncio.create_task(
        serve_health(settings.health_port, lambda: dict(metrics), registry=metrics_registry),
        name="health-ingestor",
    )
```

and the equivalent in `runner.py` using the source name as the component.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/workers/test_metrics.py tests/workers/test_health_server.py -v`
Expected: all passed.

- [ ] **Step 7: Annotate the worker pods for scraping**

In `deploy/k8s/base/workers.yaml`, add to each Deployment's pod template metadata, using that worker's own health port:

```yaml
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/path: /metrics
        prometheus.io/port: "8095"
```

- [ ] **Step 8: Run the full suite, verify rendering, and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q && kubectl kustomize deploy/k8s/overlays/hetzner > /dev/null && echo OK`
Expected: 0 failed, then `OK`.

```bash
git add pyproject.toml uv.lock src/uvo_workers/metrics.py src/uvo_workers/health.py src/uvo_workers/ingestor.py src/uvo_workers/runner.py deploy/k8s/base/workers.yaml tests/workers/test_metrics.py
git commit -m "feat(workers): expose Prometheus metrics on /metrics and annotate pods for scraping"
```

---

### Task 8: Validate manifests and build every image in CI

**Files:**
- Modify: `.github/workflows/ci.yml`

CI builds only `Dockerfile.mcp` and never validates the 17 manifests, so a malformed YAML reaches ArgoCD before anyone notices.

- [ ] **Step 1: Add a manifest validation job**

Append to the `jobs:` map in `.github/workflows/ci.yml`:

```yaml
  manifests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install kubeconform
        run: |
          curl -sSL -o kubeconform.tar.gz \
            https://github.com/yannh/kubeconform/releases/download/v0.6.7/kubeconform-linux-amd64.tar.gz
          tar xf kubeconform.tar.gz kubeconform
          sudo mv kubeconform /usr/local/bin/

      - name: Render and validate manifests
        run: |
          kubectl kustomize deploy/k8s/overlays/hetzner > /tmp/rendered.yaml
          kubeconform -strict -summary \
            -schema-location default \
            -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
            /tmp/rendered.yaml

      - name: Fail if any application image is unpinned
        run: |
          if grep -E 'image:.*:(latest)$' /tmp/rendered.yaml; then
            echo "::error::Unpinned :latest image found in rendered manifests"
            exit 1
          fi
```

- [ ] **Step 2: Build every image, not just MCP**

Find the existing build step with `grep -n "Dockerfile.mcp" .github/workflows/ci.yml`, then replace that single-image step with a matrix over all four:

```yaml
  images:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        dockerfile: [Dockerfile.mcp, Dockerfile.api, Dockerfile.workers, Dockerfile.pipeline]
    steps:
      - uses: actions/checkout@v4
      - name: Build ${{ matrix.dockerfile }}
        run: docker build -f ${{ matrix.dockerfile }} -t uvo-ci-check:${{ matrix.dockerfile }} .
```

- [ ] **Step 3: Verify the validation passes locally**

Run:
```bash
kubectl kustomize deploy/k8s/overlays/hetzner > /tmp/rendered.yaml && \
  grep -E 'image:.*:latest$' /tmp/rendered.yaml; echo "unpinned-exit:$?"
```
Expected: `unpinned-exit:1` — grep found nothing, which is the passing case.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: validate rendered k8s manifests with kubeconform and build all four images"
```

---

## Done when

- All four Dockerfiles declare `USER 10001`; `docker run --entrypoint id` confirms it.
- Every Deployment renders with `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, and `capabilities.drop: ["ALL"]`.
- Three PDBs exist; every workload sets `terminationGracePeriodSeconds`.
- Five NetworkPolicies render; default-deny ingress is in place.
- Six worker readiness probes target `/readyz`; no probe targets the always-200 `/health`.
- No application image resolves to `:latest`; third-party images are digest-pinned.
- `/metrics` returns Prometheus text and worker pods carry scrape annotations.
- CI validates rendered manifests with kubeconform and builds all four images.

## Deliberately out of scope

- **HPA on Redis stream lag.** Needs KEDA or a custom-metrics adapter, and the ingestor cannot exceed one replica until Phase 2 Task 3 (`XAUTOCLAIM`) is in production and observed. Task 7 provides the prerequisite metrics.
- **Moving the MCP `TTLCache` to Redis.** This is what blocks scaling `mcp-server` past one replica; it is an application change, not a manifest change, and deserves its own plan.
- **Replacing `mongodb-atlas-local` with managed Atlas or a supported operator.** The single-replica StatefulSet on one RWO PVC is the largest SPOF in the system, but the decision is commercial as much as technical — it is one of the open questions in `deploy/README.md`.
