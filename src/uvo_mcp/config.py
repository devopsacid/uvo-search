"""MCP server configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    uvostat_api_token: str
    uvostat_base_url: str = "https://www.uvostat.sk"
    ekosystem_base_url: str = "https://datahub.ekosystem.slovensko.digital"
    ekosystem_api_token: str = ""
    ted_base_url: str = "https://api.ted.europa.eu"
    cache_ttl_search: int = 300
    cache_ttl_entity: int = 3600
    cache_ttl_detail: int = 1800
    request_timeout: float = 30.0
    max_page_size: int = 100

    model_config = {"env_file": ".env", "env_prefix": ""}
