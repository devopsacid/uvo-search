"""Entry point for the UVO MCP server."""

import sys


def main():
    from uvo_mcp.server import mcp

    transport = sys.argv[1] if len(sys.argv) > 1 else "streamable-http"
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        import uvicorn

        from uvo_mcp.server import build_http_app

        # Not mcp.run(): the app is wrapped so clients live for the whole process.
        uvicorn.run(
            build_http_app(),
            host=mcp.settings.host,
            port=mcp.settings.port,
            log_level=mcp.settings.log_level.lower(),
        )


if __name__ == "__main__":
    main()
