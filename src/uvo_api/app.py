"""FastAPI application factory for the UVO analytics API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from uvo_api.config import ApiSettings
from uvo_api.routers import contracts, dashboard, graph, ingestion, ingestion_log, procurers, search, suppliers, worker_status


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
    app.include_router(suppliers.router)
    app.include_router(procurers.router)
    app.include_router(dashboard.router)
    app.include_router(ingestion.router)
    app.include_router(ingestion_log.router)
    app.include_router(worker_status.router)
    app.include_router(search.router)
    app.include_router(graph.router)

    return app
