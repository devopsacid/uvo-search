"""Tests for NiceGUI frontend configuration."""
import os
from unittest.mock import patch
import pytest


class TestGuiSettings:
    def test_settings_loads_required_fields(self):
        env = {"STORAGE_SECRET": "test-secret-abc", "UVOSTAT_API_TOKEN": "dummy"}
        with patch.dict(os.environ, env, clear=False):
            from uvo_gui.config import GuiSettings
            s = GuiSettings(_env_file=None)
            assert s.storage_secret == "test-secret-abc"

    def test_settings_default_values(self):
        env = {"STORAGE_SECRET": "test-secret", "UVOSTAT_API_TOKEN": "dummy"}
        with patch.dict(os.environ, env, clear=False):
            from uvo_gui.config import GuiSettings
            s = GuiSettings(_env_file=None)
            assert s.mcp_server_url == "http://localhost:8000/mcp"
            assert s.gui_host == "0.0.0.0"
            assert s.gui_port == 8080

    def test_settings_override_from_env(self):
        env = {"STORAGE_SECRET": "test", "UVOSTAT_API_TOKEN": "dummy", "MCP_SERVER_URL": "http://mcp:8000/mcp", "GUI_PORT": "9090"}
        with patch.dict(os.environ, env, clear=False):
            from uvo_gui.config import GuiSettings
            s = GuiSettings(_env_file=None)
            assert s.mcp_server_url == "http://mcp:8000/mcp"
            assert s.gui_port == 9090

    def test_missing_storage_secret_raises(self):
        from pydantic import ValidationError
        from uvo_gui.config import GuiSettings
        env_without = {k: v for k, v in os.environ.items() if k != "STORAGE_SECRET"}
        with patch.dict(os.environ, env_without, clear=True):
            with pytest.raises(ValidationError):
                GuiSettings(_env_file=None)
