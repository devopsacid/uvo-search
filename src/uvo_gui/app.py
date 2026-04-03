"""NiceGUI application setup."""
from nicegui import ui
from uvo_gui.config import GuiSettings

# Import pages to register @ui.page decorators
import uvo_gui.pages.search  # noqa: F401

settings = GuiSettings()


def start() -> None:
    """Start the NiceGUI application server."""
    ui.run(
        title="UVO Search",
        storage_secret=settings.storage_secret,
        host=settings.gui_host,
        port=settings.gui_port,
    )
