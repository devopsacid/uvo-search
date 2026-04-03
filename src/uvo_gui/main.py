"""Main entry point for the UVO Search GUI to support multiprocessing properly."""

from uvo_gui.__main__ import main

if __name__ in {"__main__", "__mp_main__"}:
    main()
