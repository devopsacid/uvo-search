"""NiceGUI application setup."""

from pathlib import Path

from nicegui import app as nicegui_app
from nicegui import ui

# Import pages to register @ui.page decorators
import uvo_gui.pages.about  # noqa: F401
import uvo_gui.pages.graph  # noqa: F401
import uvo_gui.pages.procurers  # noqa: F401
import uvo_gui.pages.search  # noqa: F401
import uvo_gui.pages.suppliers  # noqa: F401
from uvo_gui.config import GuiSettings

nicegui_app.add_static_files("/static", str(Path(__file__).parent / "static"))

settings = GuiSettings()


def start() -> None:
    """Start the NiceGUI application server."""
    ui.run(
        title="UVO Search",
        storage_secret=settings.storage_secret,
        host=settings.gui_host,
        port=settings.gui_port,
    )
