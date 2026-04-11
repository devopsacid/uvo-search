"""Pipeline configuration settings."""

from typing import Literal
from pydantic_settings import BaseSettings


class PipelineSettings(BaseSettings):
    # Source APIs
    ekosystem_base_url: str = "https://datahub.ekosystem.slovensko.digital"
    ekosystem_api_token: str = ""
    ted_base_url: str = "https://api.ted.europa.eu"
    ckan_base_url: str = "https://data.slovensko.sk"  # NOTE: CKAN API no longer available here

    # Databases (required for pipeline)
    mongodb_uri: str = "mongodb://uvo:changeme@mongo:27017"
    mongodb_database: str = "uvo_search"
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # Pipeline behaviour
    pipeline_mode: Literal["recent", "historical"] = "recent"
    recent_days: int = 365
    historical_from_year: int = 2014
    cache_dir: str = "/app/cache"
    batch_size: int = 500
    neo4j_batch_size: int = 100
    crz_rate_limit: int = 55
    uvo_base_url: str = "https://www.uvo.gov.sk"
    uvo_rate_limit: float = 1.0
    uvo_request_delay: float = 0.5
    uvo_fetch_details: bool = True
    itms_base_url: str = "https://opendata.itms2014.sk"
    itms_rate_limit: float = 5.0
    request_timeout: float = 60.0

    model_config = {"env_file": ".env", "extra": "ignore"}
