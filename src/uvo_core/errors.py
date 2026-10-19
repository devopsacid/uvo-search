"""Typed errors raised by uvo_core and its delivery adapters.

Delivery layers map these to protocol-level failures in exactly one place (the
FastAPI exception handler) instead of passing ``{"error": ...}`` dicts around.
"""


class BackendUnavailable(Exception):
    """A required backing service (Mongo, Neo4j, embedder, ...) is not usable.

    Carries a short, non-sensitive ``reason`` for logs. Never embed URIs or
    credentials in it: handlers log the reason but return a generic detail.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
