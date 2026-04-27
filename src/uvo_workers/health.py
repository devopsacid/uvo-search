"""Tiny asyncio-based HTTP server for /health endpoint."""

import asyncio
import json
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


async def serve_health(port: int, snapshot: Callable[[], dict]) -> None:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readline()
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
            body = json.dumps(snapshot(), default=str).encode()
            writer.write(b"HTTP/1.1 200 OK\r\n")
            writer.write(b"Content-Type: application/json\r\n")
            writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode())
            writer.write(body)
            await writer.drain()
        except Exception as exc:
            logger.debug("health handler error: %s", exc)
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    async with server:
        await server.serve_forever()
