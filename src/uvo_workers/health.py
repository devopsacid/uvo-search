"""Tiny asyncio-based HTTP server for /health, /healthz and /readyz."""

import asyncio
import json
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_READY_PATHS = frozenset({"/readyz", "/ready"})


def default_is_ready(metrics: dict) -> bool:
    """Readiness rule: connected to Redis and no error on the last cycle.

    Liveness deliberately stays unconditional — a dependency blip must not
    cause Kubernetes to restart the pod, which would turn a transient Redis
    outage into a cluster-wide restart storm.
    """
    if not metrics.get("redis_connected", False):
        return False
    return metrics.get("last_error") is None


async def serve_health(
    port: int,
    snapshot: Callable[[], dict],
    *,
    is_ready: Callable[[dict], bool] | None = None,
) -> None:
    ready_check = is_ready or default_is_ready

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await reader.readline()
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break

            parts = request_line.decode("latin-1").split()
            path = parts[1] if len(parts) > 1 else "/"

            metrics = snapshot()
            if path in _READY_PATHS and not ready_check(metrics):
                status = b"HTTP/1.1 503 Service Unavailable\r\n"
            else:
                status = b"HTTP/1.1 200 OK\r\n"

            body = json.dumps(metrics, default=str).encode()
            writer.write(status)
            writer.write(b"Content-Type: application/json\r\n")
            writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode())
            writer.write(body)
            await writer.drain()
        except Exception as exc:
            logger.debug("health handler error: %s", exc)
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    async with server:
        await server.serve_forever()
