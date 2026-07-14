"""Public, versioned /v1 API surface.

Mounted as a standalone FastAPI sub-app so its OpenAPI schema (served at
/v1/docs) contains only the public endpoints, and so key auth + rate limiting
apply uniformly without touching the internal /api routers.
"""

from fastapi import Depends, FastAPI, Request

from uvo_api.ratelimit import enforce_rate_limit, record_usage
from uvo_api.routers.v1 import companies, contracts
from uvo_api.routers.v1.models import ErrorResponse
from uvo_api.v1_errors import ApiV1Error, api_v1_error_handler


def create_v1_app() -> FastAPI:
    app = FastAPI(
        title="UVO Public API",
        description="Slovak government procurement data — companies and contracts.",
        version="1.0.0",
        responses={
            401: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )

    app.add_exception_handler(ApiV1Error, api_v1_error_handler)

    @app.middleware("http")
    async def meter_usage(request: Request, call_next):
        response = await call_next(request)
        ctx = getattr(request.state, "api_key_ctx", None)
        if ctx is not None:
            await record_usage(ctx.key_id, request.url.path, response.status_code)
        return response

    guarded = [Depends(enforce_rate_limit)]
    app.include_router(companies.router, dependencies=guarded)
    app.include_router(contracts.router, dependencies=guarded)

    return app
