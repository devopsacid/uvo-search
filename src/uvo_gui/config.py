"""NiceGUI frontend configuration via environment variables."""
from pydantic_settings import BaseSettings


class GuiSettings(BaseSettings):
    mcp_server_url: str = "http://localhost:8000/mcp"
    storage_secret: str
    gui_host: str = "0.0.0.0"
    gui_port: int = 8080

    model_config = {"env_file": ".env", "env_prefix": "", "extra": "ignore"}
