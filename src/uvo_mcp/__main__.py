"""Entry point for the UVO MCP server."""

import sys


def main():
    from uvo_mcp.server import mcp

    transport = sys.argv[1] if len(sys.argv) > 1 else "streamable-http"
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
