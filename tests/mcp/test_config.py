"""Tests for MCP server configuration via pydantic-settings."""

import os
from unittest.mock import patch

import pytest


class TestSettings:
    def test_settings_default_values(self):
        env = {"STORAGE_SECRET": "test-secret"}
        with patch.dict(os.environ, env, clear=False):
            from uvo_mcp.config import Settings

            s = Settings()
            assert s.cache_ttl_search == 300
            assert s.cache_ttl_entity == 3600
            assert s.cache_ttl_detail == 1800
            assert s.request_timeout == 30.0
            assert s.max_page_size == 100

    def test_settings_override_from_env(self):
        env = {
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
