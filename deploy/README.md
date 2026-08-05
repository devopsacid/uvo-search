# uvo-search — Kubernetes / GitOps deployment

Kustomize base + `hetzner` overlay for the 12-service stack (14 compose
services minus `mongo-express` and `pipeline`, which are handled
differently — see below), plus an ArgoCD `Application` to sync it.

```
deploy/
├── k8s/
│   ├── base/                  # platform-agnostic manifests
│   └── overlays/hetzner/      # Hetzner-specific: storageClass, host, images
├── argocd/
│   └── application.yaml
└── README.md
```

## Prerequisites (cluster-side, install once)

- **ingress-nginx** controller (`ingressClassName: nginx` is hardcoded in `ingress.yaml`)
- **cert-manager** with a `ClusterIssuer` named `letsencrypt-prod` (or edit the annotation in `deploy/k8s/base/ingress.yaml`)
- **Hetzner Cloud CSI driver** providing the `hcloud-volumes` StorageClass (used by mongo/neo4j/redis PVCs — see `deploy/k8s/overlays/hetzner/kustomization.yaml` patches)
- **sealed-secrets** controller (or **external-secrets-operator**) — the Secret shipped here is a placeholder only, never real credentials
- ArgoCD installed with access to your git remote
- **A CNI that enforces NetworkPolicy** (Cilium, Calico, Weave, etc.). `deploy/k8s/base/networkpolicy.yaml` ships a default-deny-ingress policy with explicit allow rules; on a CNI that ignores NetworkPolicy (e.g. stock kubenet/flannel without a policy engine) these are inert and the pod network stays flat. Verify enforcement (`kubectl get pods -A | grep -Ei 'cilium|calico|weave'` or your provider's docs) before relying on them for isolation.
- NetworkPolicies assume the ingress controller runs in a namespace named `ingress-nginx` and that the CNI enforces NetworkPolicy. Verify both before relying on network isolation.

## Excluded from this deployment

- **mongo-express**: dev-only DB admin UI, not meant to be internet-facing. Run it locally with `kubectl port-forward` + a temporary `kubectl run mongo-express` pod if you need it, or add it back under a separate low-trust overlay if you really want it in-cluster.
- **pipeline** (legacy one-shot backfill): not a long-running service, so no Deployment. `deploy/k8s/base/pipeline-job.yaml` provides a `batch/v1` `Job` you run manually and delete/recreate between runs (Jobs are immutable). It is deliberately **not** in `base/kustomization.yaml`'s resource list, so ArgoCD's automated sync will never re-trigger a backfill on every reconcile. Run it with:
  ```bash
  kubectl apply -f deploy/k8s/base/pipeline-job.yaml -n uvo-search
  kubectl logs -f job/uvo-pipeline-backfill -n uvo-search
  kubectl delete job uvo-pipeline-backfill -n uvo-search   # before re-running
  ```

## Image build & push

Four images map 1:1 to the existing Dockerfiles at repo root / `src/uvo-gui-react/`:

| Image | Dockerfile | Compose services it replaces |
|---|---|---|
| `REGISTRY_PLACEHOLDER/uvo-search-mcp` | `Dockerfile.mcp` | mcp-server |
| `REGISTRY_PLACEHOLDER/uvo-search-api` | `Dockerfile.api` | api |
| `REGISTRY_PLACEHOLDER/uvo-search-gui-react` | `src/uvo-gui-react/Dockerfile` | gui-react |
| `REGISTRY_PLACEHOLDER/uvo-search-workers` | `Dockerfile.workers` | all 4 extractors + ingestor + dedup-worker (same image, different `args:`) |
| `REGISTRY_PLACEHOLDER/uvo-search-pipeline` | `Dockerfile.pipeline` | legacy `pipeline` Job only |

```bash
REGISTRY=registry.example.com/uvo-search   # <-- your real registry
TAG=$(git rev-parse --short HEAD)

docker build -f Dockerfile.mcp -t $REGISTRY/uvo-search-mcp:$TAG .
docker build -f Dockerfile.api -t $REGISTRY/uvo-search-api:$TAG .
docker build -f Dockerfile.workers -t $REGISTRY/uvo-search-workers:$TAG .
docker build -f Dockerfile.pipeline -t $REGISTRY/uvo-search-pipeline:$TAG .
docker build -t $REGISTRY/uvo-search-gui-react:$TAG src/uvo-gui-react

for img in mcp api workers pipeline gui-react; do
  docker push $REGISTRY/uvo-search-$img:$TAG
done
```

Then update `deploy/k8s/overlays/hetzner/kustomization.yaml`'s `images:` block
(`newName`/`newTag`) — or better, let your CI pipeline do it and let ArgoCD
Image Updater (if installed) bump tags automatically.

**gui-react caveat**: its nginx config (`nginx.conf`, baked into the image at
build time) hardcodes `proxy_pass http://api:8001;`. The in-cluster `api`
Service must be named exactly `api` (it is, in `deploy/k8s/base/api.yaml`) or
the gui-react image needs to be rebuilt with a templated upstream.

## Secret bootstrapping

`deploy/k8s/base/secret.template.yaml` documents every key the workloads
expect (mirrors `.env.example` 1:1) but is **excluded** from
`base/kustomization.yaml`. `deploy/k8s/overlays/hetzner/secret.placeholder.yaml`
is a second placeholder, included in the overlay only so `kubectl kustomize`
renders end-to-end for review — its values are inert (`CHANGEME`, empty
strings), never apply it to a real cluster as-is.

Recommended real workflow (sealed-secrets):

```bash
kubectl create secret generic uvo-search-secrets -n uvo-search \
  --from-literal=MONGO_PASSWORD='...' \
  --from-literal=MONGODB_URI='mongodb://uvo:...@mongo:27017' \
  --from-literal=API_MONGODB_URI='mongodb://uvo:...@mongo:27017' \
  --from-literal=NEO4J_PASSWORD='...' \
  --from-literal=REDIS_PASSWORD='' \
  --from-literal=EKOSYSTEM_API_TOKEN='' \
  --dry-run=client -o yaml | kubeseal -o yaml > deploy/k8s/overlays/hetzner/secret.sealed.yaml
```

Then replace `secret.placeholder.yaml` with `secret.sealed.yaml` in that
overlay's `resources:` list — a `SealedSecret` is safe to commit since only
the in-cluster sealed-secrets controller can decrypt it. If you'd rather use
external-secrets-operator, swap it for an `ExternalSecret` resource pointing
at your Vault/1Password/AWS-SM store instead; the target Secret name/keys
must stay `uvo-search-secrets` / the same key names so nothing else changes.

## First sync

```bash
# 1. Point the Application at your real repo
$EDITOR deploy/argocd/application.yaml   # set spec.source.repoURL, targetRevision

# 2. Set your real domain
$EDITOR deploy/k8s/overlays/hetzner/kustomization.yaml   # ingress host patch
$EDITOR deploy/k8s/base/ingress.yaml                      # (or just rely on the overlay patch)

# 3. Render + review locally before trusting ArgoCD
kubectl kustomize deploy/k8s/overlays/hetzner | less

# 4. Bootstrap secrets (see above), commit the sealed/external secret, push

# 5. Apply the Application object (one-time; ArgoCD then owns the sync)
kubectl apply -f deploy/argocd/application.yaml

# 6. Watch it come up in wave order
argocd app get uvo-search
argocd app sync uvo-search   # only needed if automated sync is paused
kubectl get pods -n uvo-search -w
```

Expect roughly this startup order (enforced by `argocd.argoproj.io/sync-wave`
annotations on the resources, mirroring compose's `depends_on`):
`Namespace/ConfigMap/Secret` → `mongo/neo4j/redis` → `mcp-server` →
`api + 4 extractors + ingestor + dedup-worker` → `gui-react + Ingress`.

## Known caveats

- **MongoDB Atlas Local cold start**: `uvo_mcp` creates Atlas Search indexes
  on startup. On a *fresh* PVC this can take noticeably longer than the
  readiness probe's `failureThreshold` allows for the very first boot —
  watch `kubectl logs -f statefulset/mongo -n uvo-search` and
  `kubectl logs -f deploy/mcp-server -n uvo-search` if `mcp-server` seems
  stuck in `CrashLoopBackOff` right after a fresh volume is provisioned;
  it usually just needs one or two more probe cycles, not a real fix.
- **mongodb-atlas-local bundles mongod + mongot in one container** — there
  is no separate search-indexer container/sidecar to deploy; that's already
  handled by the base image compose used, and this manifest set keeps that
  1-container-per-replica shape.
- **Neo4j `NEO4J_AUTH`**: compose sets it as a single `neo4j/<password>`
  string. Kubernetes secrets can't concatenate values into one env var, so
  `deploy/k8s/base/neo4j.yaml` overrides the container `command:` to compose
  `NEO4J_AUTH` from the `NEO4J_PASSWORD` secret key at startup before
  exec'ing the real entrypoint. If you upgrade the neo4j image and its
  entrypoint script path changes, this override breaks silently — verify
  `/startup/docker-entrypoint.sh` still exists in whatever `neo4j:5.x` tag
  you pin.
- **Single-replica stateful workloads by design**: `mongo`, `neo4j`, `redis`
  are all `replicas: 1` StatefulSets with `ReadWriteOnce` PVCs — this
  mirrors the current compose setup exactly (no replica sets / clustering
  configured in the app), not a k8s limitation. See "Open questions" below
  for whether managed databases would be a better fit for production.
- **`ingestor` and `dedup-worker` kept at `replicas: 1`**: the Redis
  Streams consumer-group code in `uvo_workers` was not verified safe for
  concurrent consumers in this pass — scaling these without checking
  consumer-group ID assignment first could double-process or drop events.
- **Extractors have no Service**: they only expose `/health` for
  probes and don't need `ClusterIP` DNS from anything else, keeping the
  manifest set smaller. Add one back trivially if you want to scrape
  `/health` externally (e.g. via a Prometheus `PodMonitor` instead of a
  `Service` + `ServiceMonitor`).
- **`hcloud-volumes` StorageClass name is asserted, not verified** — if
  your Hetzner CSI install uses a different StorageClass name (e.g. it
  ships a `WaitForFirstConsumer` variant under another name), edit the
  `patches:` block in `deploy/k8s/overlays/hetzner/kustomization.yaml`.
- No `docker-troubleshoot` skill file was found in this repo at review
  time (`.claude/skills/docker-troubleshoot/` does not exist) — the
  compose/volume gotchas above were derived directly from
  `docker-compose.yml`, the Dockerfiles, and `.env.example` instead.

## Open questions for you

1. **Real domain**: `uvo.example.com` is a placeholder in both
   `deploy/k8s/base/ingress.yaml` and the `hetzner` overlay patch — what's
   the actual hostname?
2. **Registry**: `REGISTRY_PLACEHOLDER` needs your actual registry
   (GitHub Container Registry? GitLab registry? Hetzner-hosted?).
3. **Replica counts**: `gui-react` defaults to `2`; everything else to `1`
   (matching compose, which has no scaling story at all). Do you want
   `api`/`mcp-server` at `2` for zero-downtime rollouts, given they're
   stateless behind a Service?
4. **Managed databases vs in-cluster**: this deployment replicates compose
   as-is — `mongo`/`neo4j`/`redis` all run in-cluster on hcloud-volumes with
   no backup/replication story. For production, consider MongoDB Atlas
   (managed, already using the Atlas image locally so migration is
   low-friction) and/or Neo4j Aura instead of self-managed StatefulSets —
   trades operational burden for cost and an external network hop.
5. **`EKOSYSTEM_API_TOKEN`**: currently optional/empty in `.env.example`.
   Do any environments actually set it? If so it needs adding to the real
   sealed secret.
6. **ArgoCD project**: `application.yaml` uses `project: default` — do you
   want a dedicated ArgoCD `AppProject` scoping RBAC/allowed destinations
   for this app instead?
7. **`mongo-express` in a private/VPN-only context**: excluded entirely
   here per the task brief, but if you want occasional DB-browsing access,
   worth deciding now whether that's a `kubectl port-forward` habit or a
   genuinely separate low-trust overlay with its own auth in front.
