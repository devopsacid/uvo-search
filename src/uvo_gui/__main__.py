"""Entry point for the UVO Search NiceGUI frontend."""

from uvo_gui.app import start


def main() -> None:
    start()


if __name__ in {"__main__", "__mp_main__"}:
    main()
