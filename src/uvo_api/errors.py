"""Uniform error handling for uvo_core-backed routes.

The API used to hop through the MCP server; a failed hop raised McpToolError
and returned an {"error": ..., "status_code": ...} envelope that routers had
to check by hand. That hop is gone (routers call uvo_core.services in-process
via run_query / the repository ports), but the same two failure shapes remain:

  1. A degraded-but-handled dependency (Neo4j down, embedder unavailable)
     still comes back as an {"error": ...} envelope from run_query.
  2. A genuine backend outage (Mongo unreachable, driver exception) now
     raises instead of returning a dict, and would otherwise surface as a
     bare 500 whose detail can embed a connection string.

Both must become a 5xx with a generic, non-leaking detail — never a silent
empty 200, and never the raw exception/driver message.
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_GENERIC_DETAIL = "Backend temporarily unavailable"


def raise_for_tool_error(result: dict, tool_name: str) -> dict:
    """Convert a run_query error envelope into an HTTP error.

    Call sites that read `result.get("items", [])` without checking for an
    "error" key silently turn a backend outage into an empty 200. Wrapping
    the result here makes that impossible to forget.
    """
    if isinstance(result, dict) and result.get("error"):
        status_code = int(result.get("status_code", 503))
        logger.error("query %s returned error envelope: %s", tool_name, result["error"])
        raise HTTPException(status_code=status_code, detail=_GENERIC_DETAIL)
    return result


def register_error_handlers(app: FastAPI) -> None:
    """Map unhandled backend exceptions to 503 without leaking details.

    HTTPException (including the ones raised by raise_for_tool_error above)
    is already handled by FastAPI's own handler and is unaffected by this
    catch-all — Starlette dispatches to the most specific registered handler.
    """

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Full detail to the server log only — driver messages for Mongo/Neo4j
        # connection failures embed URIs with credentials.
        logger.error("Unhandled error for %s: %s", request.url.path, exc, exc_info=True)
        return JSONResponse(status_code=503, content={"detail": _GENERIC_DETAIL})
