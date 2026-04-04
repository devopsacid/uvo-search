from uvo_api.config import ApiSettings


def test_default_port():
    settings = ApiSettings(mcp_server_url="http://localhost:8000/mcp")
    assert settings.port == 8001


def test_mcp_server_url_required():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ApiSettings()
