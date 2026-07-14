"""Error type and handler for the public /v1 API.

The public surface uses a documented error model: ``{"error": {"code", "message"}}``.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiV1Error(Exception):
    """Domain error rendered as the public ``{"error": {...}}`` envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
        extra: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        self.extra = extra or {}


async def api_v1_error_handler(_: Request, exc: ApiV1Error) -> JSONResponse:
    body = {"error": {"code": exc.code, "message": exc.message, **exc.extra}}
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)
