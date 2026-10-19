"""MCP server configuration via environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ekosystem_base_url: str = "https://datahub.ekosystem.slovensko.digital"
    ekosystem_api_token: str = ""
    ted_base_url: str = "https://api.ted.europa.eu"
    cache_ttl_search: int = 300
    cache_ttl_entity: int = 3600
    cache_ttl_detail: int = 1800
    request_timeout: float = 30.0
    max_page_size: int = 100

    # Database connections (optional — enables DB query path when set)
    mongodb_uri: str | None = None
    mongodb_database: str = "uvo_search"
    neo4j_uri: str | None = None
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None

    # Redis — only used by the notices:written cache-invalidation subscriber.
    # Best-effort: when unreachable the in-process caches simply expire by TTL.
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""

    # Client bounds (explicit timeouts/pools; see uvo_core.infra.clients).
    mongo_server_selection_timeout_ms: int = 5_000
    mongo_connect_timeout_ms: int = 5_000
    mongo_max_pool_size: int = 50
    neo4j_connection_timeout: float = 5.0
    neo4j_max_pool_size: int = 50
    redis_socket_connect_timeout: float = 5.0

    model_config = {
        "env_file": ".env",
        "env_prefix": "",
        "secrets_dir": "/run/secrets",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """One Settings construction per process (cached factory idiom)."""
    return Settings()
