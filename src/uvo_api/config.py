"""Analytics API configuration via environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: list[str] = ["http://localhost:5174", "http://localhost:8080"]

    # Mongo connection (read from API_MONGODB_URI / API_MONGODB_DATABASE due to env_prefix below).
    # No default: a missing URI must fail at startup rather than silently using
    # a known-weak credential.
    mongodb_uri: str
    mongodb_database: str = "uvo_search"

    # Neo4j — used in-process by the graph endpoints (optional; graph degrades to 503 when unset).
    neo4j_uri: str | None = None
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None

    # Redis — used by the public /v1 API for rate limiting and usage metering.
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""

    # Client bounds (explicit timeouts/pools; see uvo_core.infra.clients). Read from
    # API_MONGO_* / API_NEO4J_* / API_REDIS_* — all optional, defaults are production-safe.
    mongo_server_selection_timeout_ms: int = 5_000
    mongo_connect_timeout_ms: int = 5_000
    mongo_max_pool_size: int = 50
    neo4j_connection_timeout: float = 5.0
    neo4j_max_pool_size: int = 50
    redis_socket_timeout: float = 5.0
    redis_socket_connect_timeout: float = 5.0

    # Bearer token guarding operational endpoints (ingestion, ingestion-log,
    # worker-status). Empty means those routes are disabled entirely.
    ops_token: str = ""

    # Interactive docs enumerate every route including operational ones.
    # Off in production; enable explicitly for local development.
    docs_enabled: bool = False

    model_config = {
        "env_file": ".env",
        "env_prefix": "API_",
        "secrets_dir": "/run/secrets",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> ApiSettings:
    """One ApiSettings construction per process (cached factory idiom)."""
    return ApiSettings()
