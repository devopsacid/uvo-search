"""FastAPI application factory for the UVO analytics API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from uvo_api.config import ApiSettings
from uvo_api.routers import contracts


def create_app() -> FastAPI:
    settings = ApiSettings()

    app = FastAPI(
        title="UVO Analytics API",
        description="Aggregated analytics endpoints for Slovak government procurement data",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "uvo-api"}

    app.include_router(contracts.router)

    return app
