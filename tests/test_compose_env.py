"""docker-compose.yml wiring that crash-looped services when missing (QA)."""

from pathlib import Path

import pytest
import yaml

COMPOSE = yaml.safe_load((Path(__file__).parent.parent / "docker-compose.yml").read_text())
SERVICES = COMPOSE["services"]

# Everything that talks to Redis with the unprefixed REDIS_PASSWORD setting.
REDIS_CLIENTS = [
    "mcp-server",
    "extractor-vestnik",
    "extractor-crz",
    "extractor-ted",
    "extractor-itms",
    "ingestor",
    "dedup-worker",
]


@pytest.mark.parametrize("name", REDIS_CLIENTS)
def test_redis_clients_default_the_unprefixed_password(name):
    env = SERVICES[name]["environment"]
    assert env["REDIS_PASSWORD"] == "${REDIS_PASSWORD:-uvo_redis_dev}"


def test_api_gets_build_sha_for_build_info():
    assert SERVICES["api"]["environment"]["GIT_SHA"] == "${GIT_SHA:-unknown}"
