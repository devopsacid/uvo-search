"""Bounded MongoDB reachability probe shared by the API and MCP readiness endpoints."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Kubernetes readiness probes time out in a few seconds; never hang past that.
DEFAULT_PING_TIMEOUT_S = 2.0


async def mongo_ready(db, timeout: float = DEFAULT_PING_TIMEOUT_S) -> bool:
    """True when ``db`` answers a ``ping`` within ``timeout`` seconds.

    Never raises: an unreachable/slow server (or a missing handle) is "not ready",
    logged at WARNING so the cause is visible without leaking it to the caller.
    """
    if db is None:
        logger.warning("readiness: no MongoDB handle configured")
        return False
    try:
        await asyncio.wait_for(db.command("ping"), timeout=timeout)
    except TimeoutError:
        logger.warning("readiness: MongoDB ping timed out after %.1fs", timeout)
        return False
    except Exception as exc:  # noqa: BLE001 - any driver failure means not ready
        logger.warning("readiness: MongoDB ping failed: %s", exc)
        return False
    return True
