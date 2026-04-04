"""Entry point for the UVO analytics API."""

import uvicorn

from uvo_api.config import ApiSettings


def main() -> None:
    settings = ApiSettings()
    uvicorn.run(
        "uvo_api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
