from uvo_api.config import ApiSettings


def test_default_port():
    settings = ApiSettings()
    assert settings.port == 8001


def test_constructs_without_mcp_server_url():
    """The API no longer hops through the MCP server, so no MCP URL is required."""
    settings = ApiSettings()
    assert not hasattr(settings, "mcp_server_url")
