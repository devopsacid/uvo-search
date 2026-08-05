# Phase 1 — Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every deployment-blocking security finding so the stack can be exposed publicly on Hetzner k8s without handing an attacker the data plane.

**Architecture:** The Critical findings all stem from `docker-compose.yml` publishing datastores to the host with `${VAR:-changeme}` defaults. We remove host exposure, make missing secrets a hard failure rather than a silent weak default, authenticate the operational endpoints, stop persisting raw exception strings into a publicly-served collection, and harden the XML/ZIP ingestion path. No architectural change — these are surgical, mostly-config edits.

**Tech Stack:** Docker Compose, FastAPI, Pydantic Settings, lxml, Redis, nginx-ingress.

## Global Constraints

- Python 3.12+; all commands run through `uv run`.
- **Prerequisite:** Phase 0 (test suite repair) must be complete. Do not start with a red suite — you will not be able to tell your changes from pre-existing failures.
- Every task ends with `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q` green.
- Never write a real credential into any tracked file. Placeholders only.
- Conventional Commits (`fix:`, `feat:`, `chore:`, `docs:`).
- The compose file after this plan is **development-only**. Production deploys come from `deploy/k8s/`.

---

### Task 1: Stop publishing datastores to the host

**Files:**
- Modify: `docker-compose.yml` — `mongo` (ports block), `neo4j` (ports block), `redis` (ports block), `mcp-server` (ports block), `mongo-express` (whole service)

**Interfaces:**
- Produces: after this task, only `api` (8001) and `gui-react` (8080) publish to the host. Every other service is reachable only on the compose network by service name. Tasks in Phase 3 rely on this same topology being enforced by NetworkPolicy in k8s.

- [ ] **Step 1: Record the current exposure as a baseline**

Run: `docker compose config --services && grep -n -A2 'ports:' docker-compose.yml`
Expected: shows published `8000`, `27017`, `7474`, `7687`, `6379`, `8081`.

- [ ] **Step 2: Bind the datastore ports to loopback instead of all interfaces**

Development still wants local access to Mongo/Neo4j; the fix is to bind them to `127.0.0.1` so they are never reachable from off-host. Edit each `ports:` block:

```yaml
  mongo:
    ports:
      - "127.0.0.1:27017:27017"

  neo4j:
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"

  redis:
    ports:
      - "127.0.0.1:6379:6379"

  mcp-server:
    ports:
      - "127.0.0.1:8000:8000"
```

- [ ] **Step 3: Move `mongo-express` behind an opt-in profile**

Add a `profiles:` key to the `mongo-express` service so it never starts with a plain `docker compose up`, and bind it to loopback:

```yaml
  mongo-express:
    image: mongo-express:latest
    profiles: ["debug"]
    restart: unless-stopped
    ports:
      - "127.0.0.1:8081:8081"
```

Leave the rest of the service definition unchanged.

- [ ] **Step 4: Verify mongo-express no longer starts by default**

Run: `docker compose config --services`
Expected: `mongo-express` is absent. Then run `docker compose --profile debug config --services` and expect it to be present.

- [ ] **Step 5: Verify no service binds to all interfaces except api and gui-react**

Run: `docker compose config | grep -n "published"`
Expected: every entry except the `api` (8001) and `gui-react` (8080) mappings shows `host_ip: 127.0.0.1`.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "fix(security): bind datastores to loopback and gate mongo-express behind a debug profile"
```

---

### Task 2: Enable Redis authentication

**Files:**
- Modify: `docker-compose.yml` — `redis` service `command`
- Modify: `.env.example:41`
- Modify: `deploy/k8s/base/redis.yaml` — StatefulSet container `command`/`args`
- Read: `src/uvo_pipeline/redis_client.py`

Redis currently runs with no `--requirepass` at all, in both compose and k8s, even though `REDIS_PASSWORD` is already plumbed through `RedisSettings` and consumed at `redis_client.py:19-20`. Only the server side is missing.

- [ ] **Step 1: Confirm the client already sends the password**

Run: `grep -n "password" src/uvo_pipeline/redis_client.py`
Expected: shows `password=` being passed to the Redis constructor, resolved from `RedisSettings.redis_password`. If the client does not send a password, STOP and add that first — enabling `requirepass` without a client-side password locks every worker out.

- [ ] **Step 2: Require a password in the compose Redis command**

Change the `redis` service `command`:

```yaml
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command:
      ["redis-server", "--appendonly", "yes", "--requirepass", "${REDIS_PASSWORD:?REDIS_PASSWORD must be set}"]
```

The `:?` form makes an unset or empty `REDIS_PASSWORD` abort `docker compose up` with the given message, rather than silently starting an unauthenticated Redis.

- [ ] **Step 3: Document a non-empty placeholder in `.env.example`**

Change the `REDIS_PASSWORD=` line to carry a placeholder plus generation guidance:

```bash
# Redis AUTH — REQUIRED. Generate with: openssl rand -base64 36
REDIS_PASSWORD=changeme-generate-with-openssl-rand
```

- [ ] **Step 4: Require a password in the k8s StatefulSet**

In `deploy/k8s/base/redis.yaml`, change the container spec so the server reads the password from the existing Secret:

```yaml
        command: ["redis-server"]
        args:
          - "--appendonly"
          - "yes"
          - "--requirepass"
          - "$(REDIS_PASSWORD)"
        env:
          - name: REDIS_PASSWORD
            valueFrom:
              secretKeyRef:
                name: uvo-secrets
                key: REDIS_PASSWORD
```

Use the exact Secret name and key already present in `deploy/k8s/base/secret.template.yaml` — run `grep -n "REDIS_PASSWORD\|^  name:" deploy/k8s/base/secret.template.yaml` to confirm both before editing.

- [ ] **Step 5: Fix the Redis liveness probe to authenticate**

An exec probe running bare `redis-cli ping` returns `NOAUTH` once `requirepass` is on, which would fail the probe forever. In the same file, change the probe command to:

```yaml
        livenessProbe:
          exec:
            command: ["sh", "-c", 'redis-cli -a "$REDIS_PASSWORD" ping | grep -q PONG']
```

Apply the same change to the compose `redis` healthcheck:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "redis-cli -a \"$$REDIS_PASSWORD\" ping | grep -q PONG"]
```

- [ ] **Step 6: Verify the manifests still render**

Run: `kubectl kustomize deploy/k8s/overlays/hetzner > /dev/null && echo RENDER_OK`
Expected: `RENDER_OK`, exit 0.

- [ ] **Step 7: Verify compose refuses to start without the variable**

Run: `REDIS_PASSWORD= docker compose config > /dev/null; echo "EXIT:$?"`
Expected: non-zero exit with the message `REDIS_PASSWORD must be set`.

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml .env.example deploy/k8s/base/redis.yaml
git commit -m "fix(security): require Redis AUTH in compose and k8s, fix probes to authenticate"
```

---

### Task 3: Make weak default credentials impossible

**Files:**
- Modify: `docker-compose.yml` — every `${VAR:-changeme}` occurrence
- Modify: `src/uvo_pipeline/config.py:16,20`
- Modify: `src/uvo_api/config.py:13`
- Test: `tests/pipeline/test_config_no_default_secrets.py` (create)

A `:-changeme` shell default means an operator who forgets to set the variable gets a guessable password instead of a crash. The same literal is hardcoded as a Pydantic field default, so the application itself will happily run with it.

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_config_no_default_secrets.py`:

```python
"""No settings class may carry a usable credential as its default value.

A weak default means a misconfigured deployment starts successfully with a
guessable password instead of failing loudly. Credentials must come from the
environment or the process must not start.
"""

import inspect

import pytest

from uvo_api.config import ApiSettings
from uvo_pipeline.config import PipelineSettings

FORBIDDEN = ("changeme", "password", "secret123", "admin")


@pytest.mark.parametrize("settings_cls", [PipelineSettings, ApiSettings])
def test_no_weak_credential_defaults(settings_cls):
    source = inspect.getsource(settings_cls)
    for token in FORBIDDEN:
        assert token not in source.lower(), (
            f"{settings_cls.__name__} contains the literal {token!r} as a default; "
            "credentials must be supplied via the environment"
        )


def test_compose_has_no_weak_defaults():
    with open("docker-compose.yml", encoding="utf-8") as fh:
        compose = fh.read()
    assert ":-changeme" not in compose, (
        "docker-compose.yml uses ${VAR:-changeme}; use ${VAR:?message} so an "
        "unset variable aborts startup instead of yielding a known password"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/pipeline/test_config_no_default_secrets.py -v`
Expected: FAIL — all three tests, reporting `changeme` present in both settings classes and in the compose file.

- [ ] **Step 3: Remove the credential defaults from the settings classes**

In `src/uvo_pipeline/config.py`, make the two credential-bearing fields required by removing their defaults:

```python
    # Databases (required for pipeline) — no defaults: a missing value must
    # fail at startup rather than silently using a known-weak credential.
    mongodb_uri: str
    mongodb_database: str = "uvo_search"
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str
```

In `src/uvo_api/config.py`, do the same for the Mongo URI:

```python
    # Mongo connection — shared with uvo_pipeline (no API_ prefix for URI to match pipeline env)
    mongodb_uri: str
    mongodb_database: str = "uvo_search"
```

Pydantic Settings raises `ValidationError` at construction when a field with no default is absent from the environment — which is exactly the desired hard failure.

- [ ] **Step 4: Replace every compose `:-changeme` with a hard failure**

In `docker-compose.yml`, change each occurrence:

```yaml
  mongo:
    environment:
      MONGODB_INITDB_ROOT_USERNAME: uvo
      MONGODB_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD:?MONGO_PASSWORD must be set}

  neo4j:
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:?NEO4J_PASSWORD must be set}

  mongo-express:
    environment:
      ME_CONFIG_MONGODB_ADMINPASSWORD: ${MONGO_PASSWORD:?MONGO_PASSWORD must be set}
      ME_CONFIG_MONGODB_URL: mongodb://uvo:${MONGO_PASSWORD:?MONGO_PASSWORD must be set}@mongo:27017/
      ME_CONFIG_BASICAUTH_PASSWORD: ${MONGO_PASSWORD:?MONGO_PASSWORD must be set}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/pipeline/test_config_no_default_secrets.py -v`
Expected: 3 passed.

- [ ] **Step 6: Fix any test that relied on the removed defaults**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed. If tests now fail constructing settings, set the variables in the test's `monkeypatch` fixture rather than restoring the defaults:

```python
monkeypatch.setenv("MONGODB_URI", "mongodb://test:test@localhost:27017")
monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
```

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml src/uvo_pipeline/config.py src/uvo_api/config.py tests/pipeline/test_config_no_default_secrets.py
git commit -m "fix(security): fail startup on missing credentials instead of defaulting to changeme"
```

---

### Task 4: Stop persisting raw exception strings into the public log collection

**Files:**
- Modify: `src/uvo_workers/runner.py:147`
- Modify: `src/uvo_workers/ingestor.py:223`
- Test: `tests/workers/test_error_redaction.py` (create)

`runner.py:147` builds `error = f"{type(exc).__name__}: {exc}"` and persists it via `_log_cycle_result` into `ingestion_log`, which `/api/dashboard/ingestion-log` serves to anonymous users. A driver connection failure embeds the full `mongodb://user:pass@host` DSN in `str(exc)`. The exception *type* is the operationally useful part; the message goes to stderr only.

- [ ] **Step 1: Write the failing test**

Create `tests/workers/test_error_redaction.py`:

```python
"""Exception detail must never reach the publicly-served ingestion_log.

/api/dashboard/ingestion-log is anonymous. pymongo and redis-py embed the
full connection URI — including credentials — in their exception messages,
so only the exception type may be persisted.
"""

from uvo_workers.errors import redact_exception


def test_redacts_message_keeps_type():
    exc = ConnectionError("connection to mongodb://uvo:s3cret@mongo:27017 refused")
    assert redact_exception(exc) == "ConnectionError"


def test_does_not_leak_credentials():
    exc = RuntimeError("auth failed for redis://:hunter2@redis:6379")
    result = redact_exception(exc)
    assert "hunter2" not in result
    assert "redis://" not in result


def test_handles_exception_with_empty_message():
    assert redact_exception(ValueError()) == "ValueError"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/workers/test_error_redaction.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'uvo_workers.errors'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/uvo_workers/errors.py`:

```python
"""Error formatting helpers for worker logging."""


def redact_exception(exc: BaseException) -> str:
    """Return a safe identifier for an exception, suitable for public logs.

    Only the exception class name is returned. Driver exceptions routinely
    embed connection URIs containing credentials in str(exc), and the
    ingestion_log collection is served by an unauthenticated endpoint.
    Log the full detail to stderr instead.
    """
    return type(exc).__name__
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/workers/test_error_redaction.py -v`
Expected: 3 passed.

- [ ] **Step 5: Use it at both persistence sites**

In `src/uvo_workers/runner.py`, add the import and change the error construction so the full message is logged locally but only the type is persisted:

```python
from uvo_workers.errors import redact_exception
```

```python
                    except Exception as exc:
                        logger.error("%s: extract error: %s", source, exc, exc_info=True)
                        error = redact_exception(exc)
                        metrics["last_error"] = error
```

In `src/uvo_workers/ingestor.py`, apply the same pattern at the write-failure handler:

```python
                except Exception as exc:
                    logger.error(
                        "ingestor: write failed for %s, not acking: %s",
                        stream_name, exc, exc_info=True,
                    )
                    msg = redact_exception(exc)
                    metrics["last_error"] = msg
```

Leave the rest of both handlers unchanged — `msg` continues to flow into `log_event(..., message=msg)`.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed. If an existing logging test asserts on the old `"Type: message"` format, update its expectation to the bare type name.

- [ ] **Step 7: Commit**

```bash
git add src/uvo_workers/errors.py src/uvo_workers/runner.py src/uvo_workers/ingestor.py tests/workers/test_error_redaction.py
git commit -m "fix(security): persist exception type only, keep detail in stderr logs"
```

---

### Task 5: Authenticate the operational endpoints

**Files:**
- Create: `src/uvo_api/auth.py`
- Modify: `src/uvo_api/config.py` (add `ops_token`)
- Modify: `src/uvo_api/routers/ingestion.py`, `ingestion_log.py`, `worker_status.py` (add router dependency)
- Test: `tests/api/test_ops_auth.py` (create)

Three routes expose worker topology, instance UUIDs, and error strings anonymously. They gain a bearer-token dependency; the public read routes are untouched.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_ops_auth.py`:

```python
"""Operational endpoints require a bearer token; public endpoints do not."""

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

OPS_PATHS = [
    "/api/dashboard/ingestion",
    "/api/dashboard/ingestion-log",
    "/api/dashboard/worker-status",
]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    monkeypatch.setenv("API_MONGODB_URI", "mongodb://test:test@localhost:27017")
    monkeypatch.setenv("API_OPS_TOKEN", "test-ops-token")
    return TestClient(create_app())


@pytest.mark.parametrize("path", OPS_PATHS)
def test_ops_endpoint_rejects_anonymous(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", OPS_PATHS)
def test_ops_endpoint_rejects_wrong_token(client, path):
    response = client.get(path, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_public_endpoint_still_anonymous(client):
    """A public route must not require the ops token."""
    assert client.get("/health").status_code == 200
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/api/test_ops_auth.py -v`
Expected: FAIL — the ops endpoints return 200 (or 500), not 401.

- [ ] **Step 3: Add the token setting**

In `src/uvo_api/config.py`, add to `ApiSettings`:

```python
    # Bearer token guarding operational endpoints (ingestion, ingestion-log,
    # worker-status). Empty means those routes are disabled entirely.
    ops_token: str = ""
```

- [ ] **Step 4: Write the dependency**

Create `src/uvo_api/auth.py`:

```python
"""Bearer-token guard for operational endpoints."""

import logging
import secrets

from fastapi import Header, HTTPException, status

from uvo_api.config import ApiSettings

logger = logging.getLogger(__name__)


async def require_ops_token(authorization: str = Header(default="")) -> None:
    """Reject requests without a valid operational bearer token.

    Uses a constant-time comparison so the token cannot be recovered by
    timing. When no token is configured the routes are refused outright
    rather than left open — failing closed is the safe default for
    endpoints that expose internal topology.
    """
    expected = ApiSettings().ops_token
    if not expected:
        logger.warning("Operational endpoint called but API_OPS_TOKEN is unset; refusing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operational endpoints are not configured",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

- [ ] **Step 5: Attach the dependency to the three routers**

In each of `src/uvo_api/routers/ingestion.py`, `ingestion_log.py`, and `worker_status.py`, add the import and put the guard on the router so it covers every current and future route in that module:

```python
from fastapi import APIRouter, Depends

from uvo_api.auth import require_ops_token
```

Then add `dependencies=[Depends(require_ops_token)]` to the existing `APIRouter(...)` construction in that file. Find it with `grep -n "APIRouter(" src/uvo_api/routers/ingestion.py` and extend the existing call rather than adding a second router — for example:

```python
router = APIRouter(prefix="/api/dashboard", tags=["ingestion"], dependencies=[Depends(require_ops_token)])
```

Preserve whatever `prefix` and `tags` the file already uses.

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/api/test_ops_auth.py -v`
Expected: 7 passed.

- [ ] **Step 7: Add the token to env templates**

Append to `.env.example`:

```bash
# Bearer token for /api/dashboard/{ingestion,ingestion-log,worker-status}.
# Generate with: openssl rand -hex 32. Unset disables those endpoints.
API_OPS_TOKEN=
```

Add the same key to `deploy/k8s/base/secret.template.yaml` with an inert placeholder, matching the formatting of the existing keys in that file.

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed. Existing tests hitting those three routes now need `API_OPS_TOKEN` set and an `Authorization` header — update them, do not weaken the guard.

- [ ] **Step 9: Commit**

```bash
git add src/uvo_api/auth.py src/uvo_api/config.py src/uvo_api/routers/ tests/api/test_ops_auth.py .env.example deploy/k8s/base/secret.template.yaml
git commit -m "feat(security): require bearer token on operational dashboard endpoints"
```

---

### Task 6: Fix CORS and disable public API docs

**Files:**
- Modify: `src/uvo_api/app.py:13-25`
- Modify: `src/uvo_api/config.py` (add `docs_enabled`)
- Modify: `deploy/k8s/base/configmap.yaml` (set `API_CORS_ORIGINS`)
- Test: `tests/api/test_app_hardening.py` (create)

`allow_credentials=True` is set on an API with no cookies or sessions — pure risk, zero benefit, and precisely the flag that turns a future permissive-origin change into a real vulnerability. `allow_methods=["*"]` is wrong for an all-GET API. `/docs` and `/openapi.json` enumerate the attack surface including the ops routes.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_app_hardening.py`:

```python
"""CORS and docs exposure hardening."""

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    monkeypatch.setenv("API_MONGODB_URI", "mongodb://test:test@localhost:27017")
    return monkeypatch


def test_docs_disabled_by_default(env):
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_enabled_when_flag_set(env):
    env.setenv("API_DOCS_ENABLED", "true")
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 200


def test_cors_does_not_allow_credentials(env):
    client = TestClient(create_app())
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-credentials") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/api/test_app_hardening.py -v`
Expected: FAIL — `/docs` returns 200 and the credentials header is present.

- [ ] **Step 3: Add the docs flag to settings**

In `src/uvo_api/config.py`, add to `ApiSettings`:

```python
    # Interactive docs enumerate every route including operational ones.
    # Off in production; enable explicitly for local development.
    docs_enabled: bool = False
```

- [ ] **Step 4: Harden the app factory**

In `src/uvo_api/app.py`, gate the docs URLs on the flag and tighten CORS:

```python
    app = FastAPI(
        title="UVO Analytics API",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # No cookies or sessions are used; credentialed CORS is pure risk.
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"],
    )
```

Preserve the existing `title`/`version` arguments the file already passes to `FastAPI(...)`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/api/test_app_hardening.py -v`
Expected: 3 passed.

- [ ] **Step 6: Set the production origin in the ConfigMap**

In `deploy/k8s/base/configmap.yaml`, add the CORS origin key alongside the existing entries, using the same placeholder host the ingress uses:

```yaml
  API_CORS_ORIGINS: '["https://uvo.example.com"]'
```

Confirm the placeholder host matches the ingress: `grep -n "host:" deploy/k8s/base/ingress.yaml`. If it differs, use the ingress value.

- [ ] **Step 7: Verify the manifests still render**

Run: `kubectl kustomize deploy/k8s/overlays/hetzner > /dev/null && echo RENDER_OK`
Expected: `RENDER_OK`.

- [ ] **Step 8: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed.

```bash
git add src/uvo_api/app.py src/uvo_api/config.py deploy/k8s/base/configmap.yaml tests/api/test_app_hardening.py
git commit -m "fix(security): disable public API docs, drop credentialed CORS, restrict methods to GET"
```

---

### Task 7: Bound pagination and constrain search wildcards

**Files:**
- Modify: `src/uvo_api/routers/contracts.py:25`, `suppliers.py:29`, `procurers.py:31` (offset bounds)
- Modify: `src/uvo_mcp/search_query.py:21-28`
- Test: `tests/mcp/test_search_query_wildcards.py` (create)
- Test: `tests/api/test_pagination_bounds.py` (create)

`offset` is `ge=0` with no upper bound, so `$skip: 50000000` is reachable anonymously. `search_query.py` passes any string containing `*` or `?` straight into an Atlas `wildcard` operator with `allowAnalyzedField: True` — a leading-wildcard query scans the full term dictionary across four analyzed fields.

- [ ] **Step 1: Write the failing wildcard test**

Create `tests/mcp/test_search_query_wildcards.py`:

```python
"""Wildcard queries must not become unbounded term-dictionary scans."""

import pytest

from uvo_mcp.search_query import build_search_stage

PATHS = ["title", "description"]


def test_leading_wildcard_is_rejected():
    """A leading * forces a full term-dictionary scan across every analyzed field."""
    stage = build_search_stage("*", PATHS)
    assert "wildcard" not in str(stage), "bare leading wildcard must not reach Atlas"


def test_short_prefix_wildcard_is_rejected():
    stage = build_search_stage("a*", PATHS)
    assert "wildcard" not in str(stage)


def test_wildcard_with_sufficient_prefix_is_allowed():
    stage = build_search_stage("bratisl*", PATHS)
    assert "wildcard" in str(stage)


def test_plain_text_query_unaffected():
    stage = build_search_stage("verejne obstaravanie", PATHS)
    assert "wildcard" not in str(stage)
    assert stage != {}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/mcp/test_search_query_wildcards.py -v`
Expected: FAIL on the first two tests — bare `*` and `a*` currently produce a `wildcard` clause.

- [ ] **Step 3: Require a literal prefix before allowing a wildcard**

In `src/uvo_mcp/search_query.py`, replace the wildcard branch:

```python
# Minimum literal characters required before the first wildcard metacharacter.
# Below this, Atlas must walk a prohibitively large share of the term
# dictionary across every analyzed path, which is a cheap DoS primitive on
# an unauthenticated endpoint.
_MIN_WILDCARD_PREFIX = 3


def _wildcard_prefix_len(q: str) -> int:
    """Number of literal characters before the first * or ? in the query."""
    candidates = [i for i in (q.find("*"), q.find("?")) if i != -1]
    return min(candidates) if candidates else len(q)


    if ("*" in q or "?" in q) and _wildcard_prefix_len(q) >= _MIN_WILDCARD_PREFIX:
        return {
            "wildcard": {
                "query": q,
                "path": path,
                "allowAnalyzedField": True,
            }
        }
```

Place `_MIN_WILDCARD_PREFIX` and `_wildcard_prefix_len` at module level, above the function containing the branch, and replace only the `if` condition inside that function. A query that fails the check falls through to the existing non-wildcard branch, so short-prefix searches still return results — they just run as ordinary text queries.

- [ ] **Step 4: Run the wildcard test to verify it passes**

Run: `uv run pytest tests/mcp/test_search_query_wildcards.py -v`
Expected: 4 passed.

- [ ] **Step 5: Write the failing pagination test**

Create `tests/api/test_pagination_bounds.py`:

```python
"""Offset must be bounded — an unbounded $skip is a cheap DoS primitive."""

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

PAGINATED_PATHS = ["/api/contracts", "/api/suppliers", "/api/procurers"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    monkeypatch.setenv("API_MONGODB_URI", "mongodb://test:test@localhost:27017")
    return TestClient(create_app())


@pytest.mark.parametrize("path", PAGINATED_PATHS)
def test_excessive_offset_is_rejected(client, path):
    response = client.get(path, params={"offset": 50_000_000})
    assert response.status_code == 422
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/api/test_pagination_bounds.py -v`
Expected: FAIL — the requests are accepted (200 or 500), not rejected with 422.

- [ ] **Step 7: Bound the offset in all three routers**

In each of `contracts.py`, `suppliers.py`, and `procurers.py`, add an upper bound to the existing `offset` query parameter. Find it with `grep -n "offset" src/uvo_api/routers/contracts.py` and add `le=10_000` to the existing `Query(...)` call, preserving its current default and description:

```python
    offset: int = Query(0, ge=0, le=10_000, description="Result offset; deep paging is bounded"),
```

Confirm the paths in `PAGINATED_PATHS` match the real route prefixes — run `grep -n "APIRouter(\|@router.get" src/uvo_api/routers/contracts.py` and adjust the test's path list if the prefix differs.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/api/test_pagination_bounds.py tests/mcp/test_search_query_wildcards.py -v`
Expected: 7 passed.

- [ ] **Step 9: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed.

```bash
git add src/uvo_api/routers/ src/uvo_mcp/search_query.py tests/api/test_pagination_bounds.py tests/mcp/test_search_query_wildcards.py
git commit -m "fix(security): bound pagination offset and require a literal prefix for wildcard search"
```

---

### Task 8: Harden XML parsing and ZIP handling

**Files:**
- Modify: `src/uvo_pipeline/extractors/vestnik_xml.py:7,27`
- Modify: `src/uvo_pipeline/utils/zip_handler.py:26-28`
- Test: `tests/pipeline/test_xml_hardening.py` (create)

`etree.parse(str(xml_path))` uses lxml defaults, which include `resolve_entities=True` — an external entity referencing `file:///app/.env` is resolved into the parsed tree and its contents are persisted into MongoDB and served publicly. Separately, `zip_handler` derives a filesystem path from a remote URL string, giving an arbitrary-write primitive if the upstream catalog is compromised.

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_xml_hardening.py`:

```python
"""XXE and path-traversal hardening for the Vestnik ingestion path."""

from pathlib import Path

from uvo_pipeline.extractors.vestnik_xml import _make_parser
from uvo_pipeline.utils.zip_handler import cache_path_for_url

XXE_DOC = """<?xml version="1.0"?>
<!DOCTYPE root [<!ENTITY xxe SYSTEM "file:///etc/hostname">]>
<root><title>&xxe;</title></root>
"""


def test_external_entities_are_not_resolved(tmp_path):
    from lxml import etree

    doc = tmp_path / "xxe.xml"
    doc.write_text(XXE_DOC, encoding="utf-8")
    tree = etree.parse(str(doc), _make_parser())
    title = tree.find("title").text or ""
    assert "/etc/hostname" not in title
    assert title.strip() == "", "external entity content must not be substituted"


def test_cache_path_ignores_remote_filename(tmp_path):
    evil = "https://example.org/a/../../../../app/src/uvo_pipeline/config.py"
    dest = cache_path_for_url(evil, tmp_path)
    assert dest.parent == tmp_path
    assert dest.suffix == ".zip"


def test_cache_path_is_stable_for_same_url(tmp_path):
    url = "https://example.org/dataset.zip"
    assert cache_path_for_url(url, tmp_path) == cache_path_for_url(url, tmp_path)


def test_cache_path_differs_for_different_urls(tmp_path):
    a = cache_path_for_url("https://example.org/a.zip", tmp_path)
    b = cache_path_for_url("https://example.org/b.zip", tmp_path)
    assert a != b
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/pipeline/test_xml_hardening.py -v`
Expected: FAIL with `ImportError: cannot import name '_make_parser'` and `cannot import name 'cache_path_for_url'`.

- [ ] **Step 3: Add the hardened parser**

In `src/uvo_pipeline/extractors/vestnik_xml.py`, add above the parsing function:

```python
def _make_parser() -> etree.XMLParser:
    """Return a parser with entity resolution and DTD loading disabled.

    lxml resolves external entities by default, which turns any XML document
    from the upstream catalog into a local-file-disclosure primitive: the
    resolved content lands in extracted fields, is written to MongoDB, and is
    then served publicly by the API.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
    )
```

Then change the parse call at line 27 to use it:

```python
        tree = etree.parse(str(xml_path), _make_parser())
```

- [ ] **Step 4: Add the safe cache-path helper**

In `src/uvo_pipeline/utils/zip_handler.py`, add:

```python
def cache_path_for_url(url: str, cache_dir: Path) -> Path:
    """Derive a cache filename from the URL hash, never from its path.

    The URL comes from the NKOD catalog response, i.e. it is remote data.
    Using its last path segment as a filename lets a malicious or compromised
    catalog entry escape cache_dir via '..' and write anywhere the process
    can reach.
    """
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    return cache_dir / f"vestnik_{url_hash}.zip"
```

Ensure `hashlib` and `from pathlib import Path` are imported in that module; add whichever is missing.

- [ ] **Step 5: Use the helper at the existing call site**

Replace the three lines at `zip_handler.py:26-28` with:

```python
    dest = cache_path_for_url(url, cache_dir)
```

Make sure `cache_dir` at that point is a `Path`; if it is a `str`, wrap it: `cache_path_for_url(url, Path(cache_dir))`.

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/pipeline/test_xml_hardening.py -v`
Expected: 4 passed.

- [ ] **Step 7: Run the full suite and commit**

Run: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`
Expected: 0 failed.

```bash
git add src/uvo_pipeline/extractors/vestnik_xml.py src/uvo_pipeline/utils/zip_handler.py tests/pipeline/test_xml_hardening.py
git commit -m "fix(security): disable XML entity resolution and derive cache paths from URL hash"
```

---

### Task 9: Rate-limit the ingress and protect the secret overlay

**Files:**
- Modify: `deploy/k8s/base/ingress.yaml` (annotations)
- Modify: `.gitignore`
- Modify: `CLAUDE.md` (compose is development-only)

- [ ] **Step 1: Add rate-limit annotations to the ingress**

In `deploy/k8s/base/ingress.yaml`, add to the existing `metadata.annotations` block, preserving the cert-manager annotation already there:

```yaml
    nginx.ingress.kubernetes.io/limit-rps: "10"
    nginx.ingress.kubernetes.io/limit-connections: "20"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "30"
```

- [ ] **Step 2: Verify the manifests still render**

Run: `kubectl kustomize deploy/k8s/overlays/hetzner | grep -c "limit-rps"`
Expected: `1`.

- [ ] **Step 3: Prevent a real secret from ever being committed**

Append to `.gitignore`:

```gitignore
# Never commit populated k8s secrets — only the inert template is tracked.
deploy/k8s/overlays/*/secret*.yaml
!deploy/k8s/base/secret.template.yaml
```

- [ ] **Step 4: Verify the ignore rule works**

Run: `git check-ignore -v deploy/k8s/overlays/hetzner/secret.placeholder.yaml`
Expected: prints the matching `.gitignore` line. Then run `git check-ignore -v deploy/k8s/base/secret.template.yaml` and expect **no output** (exit 1) — the template stays trackable.

- [ ] **Step 5: Mark compose as development-only**

In `CLAUDE.md`, under the `## Docker (local deploy)` heading, add as the first line of that section:

> **Development only.** `docker-compose.yml` binds datastores to loopback and is not a production artifact. Production deploys from `deploy/k8s/` via ArgoCD — see `deploy/README.md`.

- [ ] **Step 6: Commit**

```bash
git add deploy/k8s/base/ingress.yaml .gitignore CLAUDE.md
git commit -m "fix(security): rate-limit ingress, gitignore populated secrets, mark compose dev-only"
```

---

## Done when

- No datastore or MCP port is published on a non-loopback interface in compose; `mongo-express` requires `--profile debug`.
- Redis requires AUTH in both compose and k8s, and both probes authenticate.
- A missing `MONGO_PASSWORD`, `NEO4J_PASSWORD`, or `REDIS_PASSWORD` aborts startup; the literal `changeme` appears nowhere in `src/` or `docker-compose.yml`.
- The three operational endpoints return 401 without a valid bearer token.
- `/docs` and `/openapi.json` return 404 unless `API_DOCS_ENABLED=true`; CORS sends no credentials header and allows only GET.
- `offset` above 10 000 returns 422; a wildcard query with fewer than 3 literal leading characters does not reach Atlas.
- XML external entities are not resolved; ZIP cache paths derive from the URL hash.
- `git check-ignore` confirms populated secret overlays cannot be committed.
- Full suite green: `uv run pytest tests/mcp/ tests/api/ tests/pipeline/ tests/workers/ -q`.
