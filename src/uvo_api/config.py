"""Analytics API configuration via environment variables."""

from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    mcp_server_url: str
    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: list[str] = ["http://localhost:5174", "http://localhost:8080"]

    # Mongo connection (read from API_MONGODB_URI / API_MONGODB_DATABASE due to env_prefix below).
    mongodb_uri: str = "mongodb://uvo:changeme@mongo:27017"
    mongodb_database: str = "uvo_search"

    model_config = {"env_file": ".env", "env_prefix": "API_", "extra": "ignore"}
