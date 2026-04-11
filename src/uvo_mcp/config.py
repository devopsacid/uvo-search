"""MCP server configuration via environment variables."""

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

    model_config = {"env_file": ".env", "env_prefix": "", "extra": "ignore"}
