"""Shared fakes for worker tests: inject clients instead of patching modules."""

from mongomock_motor import AsyncMongoMockClient

from uvo_workers.clients import WorkerClients

DB_NAME = "uvo_search"


def fake_clients(redis, mongo=None, neo4j=None) -> WorkerClients:
    """WorkerClients over in-memory fakes; ``mongo`` is reusable across calls."""
    mongo = mongo or AsyncMongoMockClient()
    return WorkerClients(mongo=mongo, db=mongo[DB_NAME], redis=redis, neo4j=neo4j)
