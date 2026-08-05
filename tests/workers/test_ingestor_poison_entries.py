"""A poison entry (fails decode/validation) must be acked immediately.

Left unacked, it sits in the PEL forever and — since Phase 2 added
autoclaim_stale — gets redelivered on every idle cycle, writing a fresh
decode_failed log doc each time and never draining. The failure is already
durably logged; retrying an unparseable payload cannot succeed.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from mongomock_motor import AsyncMongoMockClient

import uvo_workers.ingestor as ingestor_mod


class _FakeNeo4jSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeNeo4jDriver:
    def session(self):
        return _FakeNeo4jSession()

    async def close(self):
        pass


class _FakeGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        return _FakeNeo4jDriver()


def _good_entry(entry_id: bytes = b"2-0") -> tuple:
    payload = {
        "source": "vestnik",
        "source_id": "V-1",
        "notice_type": "contract_award",
        "title": "Test notice",
    }
    fields = {
        b"payload": json.dumps(payload).encode(),
        b"hash": b"h",
        b"run": b"r",
    }
    return (entry_id, fields)


def _poison_entry(entry_id: bytes = b"1-0") -> tuple:
    # Not valid JSON — decode_entry's json.loads raises.
    fields = {
        b"payload": b"{not-json",
        b"hash": b"h",
        b"run": b"r",
    }
    return (entry_id, fields)


async def _never_returns() -> None:
    await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_poison_entry_is_acked_immediately(monkeypatch):
    fake_redis = fakeredis.aioredis.FakeRedis()

    monkeypatch.setattr(ingestor_mod, "AsyncIOMotorClient", AsyncMongoMockClient)
    monkeypatch.setattr(ingestor_mod, "get_redis", AsyncMock(return_value=fake_redis))
    monkeypatch.setattr(ingestor_mod, "close_redis", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "AsyncGraphDatabase", _FakeGraphDatabase)
    monkeypatch.setattr(ingestor_mod, "ensure_consumer_group", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "ensure_constraints", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "merge_notice_batch", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "publish", AsyncMock())
    monkeypatch.setattr(ingestor_mod, "upsert_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(ingestor_mod, "autoclaim_stale", AsyncMock(return_value=[]))

    ack_mock = AsyncMock()
    monkeypatch.setattr(ingestor_mod, "ack", ack_mock)

    delivered_batch = asyncio.Event()
    call_count = [0]

    async def fake_read_group(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            delivered_batch.set()
            return [("notices:vestnik", [_poison_entry(), _good_entry()])]
        await asyncio.sleep(0.01)
        return []

    monkeypatch.setattr(ingestor_mod, "read_group", fake_read_group)

    async def fake_serve_health(port, snapshot, **kwargs):
        await _never_returns()

    monkeypatch.setattr(ingestor_mod, "serve_health", fake_serve_health)

    task = asyncio.create_task(ingestor_mod.run_ingestor())
    try:
        await asyncio.wait_for(delivered_batch.wait(), timeout=10)

        # Wait for both acks (poison entry ack + successful-batch ack) to land.
        for _ in range(200):
            if ack_mock.await_count >= 2:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail(f"expected 2 ack calls, got {ack_mock.await_count}")

        acked_ids: set[bytes] = set()
        for call in ack_mock.await_args_list:
            _redis, _stream, _group, entry_ids = call.args
            acked_ids.update(entry_ids)

        assert b"1-0" in acked_ids, "the poison entry must be acked"
        assert b"2-0" in acked_ids, "the good entry must still be acked normally"
    finally:
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError, SystemExit):
            pass
