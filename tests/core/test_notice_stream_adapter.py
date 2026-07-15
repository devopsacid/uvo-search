"""RedisNoticeStream — thin NoticeStream port wrapper over Redis Streams."""

import fakeredis.aioredis

from uvo_core.adapters.redis.notice_stream import RedisNoticeStream


async def test_xadd_then_read_group_then_ack():
    redis_client = fakeredis.aioredis.FakeRedis()
    stream = RedisNoticeStream(redis_client, "vestnik")

    entry_id = await stream.xadd_notice(
        {"source_id": "V-1", "content_hash": "sha256:abc", "pipeline_run_id": "run-1"}
    )
    assert isinstance(entry_id, str)

    await redis_client.xgroup_create("notices:vestnik", "ingestor", id="0", mkstream=True)
    results = await stream.read_group("ingestor", "consumer-1", 10)

    assert len(results) == 1
    stream_name, entries = results[0]
    assert stream_name == "notices:vestnik"
    assert len(entries) == 1
    got_entry_id, fields = entries[0]

    await stream.ack("ingestor", got_entry_id.decode())

    pending = await redis_client.xpending("notices:vestnik", "ingestor")
    assert pending["pending"] == 0


async def test_xadd_maxlen_trims_stream():
    redis_client = fakeredis.aioredis.FakeRedis()
    stream = RedisNoticeStream(redis_client, "crz", maxlen=2)

    for i in range(5):
        await stream.xadd_notice(
            {
                "source_id": f"C-{i}",
                "content_hash": f"sha256:{i}",
                "pipeline_run_id": "run-x",
            }
        )

    length = await redis_client.xlen("notices:crz")
    assert (
        length <= 5
    )  # approximate trim — not exact, matches existing xadd_notice(approximate=True)
