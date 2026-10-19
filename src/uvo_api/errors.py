"""Uniform backend-failure handling for uvo_core-backed routes.

Routers call uvo_core services in-process, so a failing dependency shows up as an
exception, never as an ``{"error": ...}`` envelope:

  1. A dependency that is known to be unavailable (Neo4j not configured, ...)
     raises the typed ``uvo_core.errors.BackendUnavailable``.
  2. A genuine outage (Mongo unreachable, Neo4j connection dropped) raises the
     driver's own exception.

Both are mapped here, in one place, to a 503 with a generic, non-leaking detail —
never a silent empty 200, and never the raw exception text (driver messages for
connection failures embed URIs with credentials).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from neo4j.exceptions import DriverError, Neo4jError
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from uvo_core.errors import BackendUnavailable

logger = logging.getLogger(__name__)

GENERIC_DETAIL = "Backend temporarily unavailable"

# Exceptions that mean "a backing service is down/unreachable" (as opposed to a bug).
BACKEND_ERRORS: tuple[type[Exception], ...] = (
    BackendUnavailable,
    ConnectionFailure,  # AutoReconnect, NetworkTimeout, ...
    ServerSelectionTimeoutError,
    DriverError,
    Neo4jError,
)


def register_error_handlers(app: FastAPI) -> None:
    """Map backend exceptions (and, as a last resort, any unhandled error) to 503.

    ``HTTPException`` keeps FastAPI's own handler; Starlette dispatches to the most
    specific registered handler.
    """

    async def _handle_backend_error(request: Request, exc: Exception) -> JSONResponse:
        # Full detail to the server log only.
        logger.error("Backend unavailable for %s: %s", request.url.path, exc, exc_info=True)
        return JSONResponse(status_code=503, content={"detail": GENERIC_DETAIL})

    for exc_type in BACKEND_ERRORS:
        app.add_exception_handler(exc_type, _handle_backend_error)

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error for %s: %s", request.url.path, exc, exc_info=True)
        return JSONResponse(status_code=503, content={"detail": GENERIC_DETAIL})
