"""ApiSettings must actually receive the Redis password.

ApiSettings sets env_prefix "API_", so the unprefixed REDIS_PASSWORD used by the
workers and by the Redis server itself is invisible to it. Once Redis requires
AUTH, an unpopulated ApiSettings.redis_password makes every /v1 request fail
closed with NOAUTH and silently stops cache invalidation. This pins the wiring.
"""

import pytest

from uvo_api.config import ApiSettings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_redis_password_read_from_prefixed_var(monkeypatch):
    monkeypatch.setenv("API_REDIS_PASSWORD", "s3cret-from-env")
    assert ApiSettings().redis_password == "s3cret-from-env"


def test_unprefixed_var_is_not_enough(monkeypatch):
    """Documents the trap: the unprefixed name does NOT reach ApiSettings, which
    is exactly why compose and the k8s Deployment must map it explicitly."""
    monkeypatch.delenv("API_REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("REDIS_PASSWORD", "s3cret-from-env")
    assert ApiSettings().redis_password == ""


def test_compose_maps_api_redis_password():
    """The api service must hand ApiSettings the prefixed variable."""
    with open("docker-compose.yml", encoding="utf-8") as fh:
        compose = fh.read()
    assert "API_REDIS_PASSWORD" in compose, (
        "docker-compose.yml must set API_REDIS_PASSWORD on the api service; "
        "ApiSettings cannot see the unprefixed REDIS_PASSWORD"
    )


def test_k8s_api_deployment_maps_api_redis_password():
    with open("deploy/k8s/base/api.yaml", encoding="utf-8") as fh:
        manifest = fh.read()
    assert "API_REDIS_PASSWORD" in manifest, (
        "the api Deployment must map API_REDIS_PASSWORD from the Secret"
    )
