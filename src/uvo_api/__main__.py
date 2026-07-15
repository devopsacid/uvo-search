"""Entry point for the UVO analytics API."""

import uvicorn

from uvo_api.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "uvo_api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
