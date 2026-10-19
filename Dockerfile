# syntax=docker/dockerfile:1.7
#
# One multi-stage Dockerfile for every Python image. Pick the image with
# `--target`:
#
#   docker build --target mcp      -t uvo-mcp .       # port 8000
#   docker build --target api      -t uvo-api .       # port 8001
#   docker build --target workers  -t uvo-workers .   # 4 extractors + ingestor + dedup
#   docker build --target pipeline -t uvo-pipeline .  # legacy one-shot backfill CLI
#
# (The GUI image is src/uvo-gui-react/Dockerfile.)
#
# Layout: a shared third-party dependency layer -> a per-target build stage that
# copies only that image's first-party sources and runs the SECOND uv sync ->
# a slim runtime stage that copies the finished /app/.venv + /app/src. uv itself
# never reaches the runtime image.

ARG UV_VERSION=0.13.1
ARG PYTHON_IMAGE=python:3.12-slim

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------------------------------------------------------------------------
# Shared build base: third-party dependencies only. Identical for every target,
# so this layer (and the uv cache mount) is built once and reused.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS deps
COPY --from=uv /uv /usr/local/bin/uv

# COMPILE_BYTECODE: ship .pyc so a read-only rootfs doesn't pay the compile cost
# on every start. LINK_MODE=copy: the cache mount is a different filesystem from
# /app, so hardlinking would only emit warnings.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---------------------------------------------------------------------------
# Per-target build stages. Each COPYs its sources and then runs uv sync AGAIN.
#
# That second sync is load-bearing: the one above ran before COPY src/, so it
# resolved third-party deps only and the first-party packages never landed in
# the venv. `uv run` used to paper over this by re-syncing at container start,
# but the runtime image has no uv (and a read-only rootfs), so it must happen
# at build time. A build that succeeds proves nothing -- CI import-checks every
# image for exactly this reason.
# ---------------------------------------------------------------------------
FROM deps AS build-mcp
# Pre-download the fastembed model (~134MB) so it is available without network.
# Kept outside /tmp: k8s mounts an emptyDir over /tmp, which would hide it.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
RUN .venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"
COPY src/uvo_core/ src/uvo_core/
COPY src/uvo_mcp/ src/uvo_mcp/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && .venv/bin/python -m compileall -q src

FROM deps AS build-api
# api runs queries in-process via uvo_core and pulls health helpers from
# uvo_pipeline. It does not import uvo_mcp (the MCP hop is gone).
COPY src/uvo_core/ src/uvo_core/
COPY src/uvo_pipeline/ src/uvo_pipeline/
COPY src/uvo_api/ src/uvo_api/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && .venv/bin/python -m compileall -q src

FROM deps AS build-workers
COPY src/uvo_core/ src/uvo_core/
COPY src/uvo_pipeline/ src/uvo_pipeline/
COPY src/uvo_workers/ src/uvo_workers/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && .venv/bin/python -m compileall -q src

FROM deps AS build-pipeline
# uvo_pipeline does not import uvo_mcp; only core + pipeline are needed.
COPY src/uvo_core/ src/uvo_core/
COPY src/uvo_pipeline/ src/uvo_pipeline/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && .venv/bin/python -m compileall -q src

# ---------------------------------------------------------------------------
# Runtime bases (no uv). uid is fixed so the k8s securityContext can assert
# runAsUser without depending on image internals.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime-root
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && install -d -o 10001 -g 10001 /app
WORKDIR /app
# PYTHONUNBUFFERED: logs reach stdout immediately. The venv's bin/ is first on
# PATH so `python` and the console scripts resolve without `uv run`.
# UV_NO_SYNC / UV_CACHE_DIR are inert without uv but keep any ad-hoc `uv run`
# someone exec's into a read-only container from trying to re-sync.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    UV_NO_SYNC=1 \
    UV_CACHE_DIR=/tmp/uv-cache

# workers + pipeline additionally need libxml2 at runtime.
FROM runtime-root AS runtime-xml-root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libxml2 \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Final images. COPY --chown replaces a slow `chown -R` layer that duplicated
# the whole venv.
# ---------------------------------------------------------------------------
FROM runtime-root AS mcp
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
COPY --from=build-mcp --chown=10001:10001 /opt/fastembed /opt/fastembed
COPY --from=build-mcp --chown=10001:10001 /app/.venv /app/.venv
COPY --from=build-mcp --chown=10001:10001 /app/src /app/src
COPY --chown=10001:10001 pyproject.toml ./
USER 10001
EXPOSE 8000
CMD ["python", "-m", "uvo_mcp"]

FROM runtime-root AS api
COPY --from=build-api --chown=10001:10001 /app/.venv /app/.venv
COPY --from=build-api --chown=10001:10001 /app/src /app/src
COPY --chown=10001:10001 pyproject.toml ./
USER 10001
EXPOSE 8001
CMD ["uvo-api"]

FROM runtime-xml-root AS workers
ENV PYTHONPATH=/app/src
COPY --from=build-workers --chown=10001:10001 /app/.venv /app/.venv
COPY --from=build-workers --chown=10001:10001 /app/src /app/src
COPY --chown=10001:10001 pyproject.toml ./
RUN install -d -o 10001 -g 10001 /app/cache
USER 10001
# k8s/compose pass the module as args, e.g. ["uvo_workers.vestnik"].
ENTRYPOINT ["python", "-m"]
CMD ["uvo_workers.ingestor"]

FROM runtime-xml-root AS pipeline
COPY --from=build-pipeline --chown=10001:10001 /app/.venv /app/.venv
COPY --from=build-pipeline --chown=10001:10001 /app/src /app/src
COPY --chown=10001:10001 pyproject.toml ./
RUN install -d -o 10001 -g 10001 /app/cache
USER 10001
ENTRYPOINT ["python", "-m", "uvo_pipeline"]
CMD ["--mode=recent"]
