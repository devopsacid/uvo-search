"""NiceGUI application setup."""

from nicegui import ui

# Import pages to register @ui.page decorators
import uvo_gui.pages.about  # noqa: F401
import uvo_gui.pages.procurers  # noqa: F401
import uvo_gui.pages.search  # noqa: F401
import uvo_gui.pages.suppliers  # noqa: F401
from uvo_gui.config import GuiSettings

settings = GuiSettings()


def start() -> None:
    """Start the NiceGUI application server."""
    ui.run(
        title="UVO Search",
        storage_secret=settings.storage_secret,
        host=settings.gui_host,
        port=settings.gui_port,
    )
