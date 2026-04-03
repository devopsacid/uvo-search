"""Tests for MCP server configuration via pydantic-settings."""

import os
from unittest.mock import patch

import pytest


class TestSettings:
    def test_settings_loads_required_token(self):
        env = {"UVOSTAT_API_TOKEN": "test-token-abc123", "STORAGE_SECRET": "test-secret"}
        with patch.dict(os.environ, env, clear=False):
            from uvo_mcp.config import Settings

            s = Settings()
            assert s.uvostat_api_token == "test-token-abc123"

    def test_settings_default_values(self):
        env = {"UVOSTAT_API_TOKEN": "test-token", "STORAGE_SECRET": "test-secret"}
        with patch.dict(os.environ, env, clear=False):
            from uvo_mcp.config import Settings

            s = Settings()
            assert s.uvostat_base_url == "https://www.uvostat.sk"
            assert s.cache_ttl_search == 300
            assert s.cache_ttl_entity == 3600
            assert s.cache_ttl_detail == 1800
            assert s.request_timeout == 30.0
            assert s.max_page_size == 100

    def test_settings_override_from_env(self):
        env = {
            "UVOSTAT_API_TOKEN": "test-token",
            "STORAGE_SECRET": "test-secret",
            "CACHE_TTL_SEARCH": "600",
            "REQUEST_TIMEOUT": "15.0",
            "MAX_PAGE_SIZE": "50",
        }
        with patch.dict(os.environ, env, clear=False):
            from uvo_mcp.config import Settings

            s = Settings()
            assert s.cache_ttl_search == 600
            assert s.request_timeout == 15.0
            assert s.max_page_size == 50

    def test_settings_missing_required_token_raises(self):
        from pydantic import ValidationError

        from uvo_mcp.config import Settings

        env_without_token = {k: v for k, v in os.environ.items() if k != "UVOSTAT_API_TOKEN"}
        with patch.dict(os.environ, env_without_token, clear=True):
            with pytest.raises(ValidationError):
                # Pass _env_file=None to prevent reading from .env on disk
                Settings(_env_file=None)
