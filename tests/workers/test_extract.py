"""Generic extractor loop: per-strategy checkpoint semantics are preserved."""

from datetime import UTC, datetime

import fakeredis.aioredis
import pytest
from mongomock_motor import AsyncMongoMockClient

import uvo_workers.extract as extract_mod
from uvo_core.adapters.mongo.checkpoints import MongoCheckpointStore
from uvo_core.domain.models import CanonicalNotice
from uvo_workers.extract import (
    ExtractContext,
    MaxModifiedCheckpoint,
    MinIdCheckpoint,
    SourceSpec,
    WallClockCheckpoint,
    run_extract,
)
from uvo_workers.settings import ExtractorSettings

from .helpers import DB_NAME


class _Settings(ExtractorSettings):
    pass


def _notice(raw) -> CanonicalNotice:
    if raw.get("bad"):
        raise ValueError("untransformable")
    return CanonicalNotice(
        source="itms", source_id=str(raw["id"]), notice_type="other", title=f"t{raw['id']}"
    )


def _spec(raws, checkpoint, name="itms") -> SourceSpec:
    async def fetch(cycle):
        for raw in raws:
            if "modified" in raw:
                MaxModifiedCheckpoint.observe(cycle, raw["modified"])
            yield raw

    return SourceSpec(
        name=name, settings=_Settings, fetch=fetch, transform=_notice, checkpoint=checkpoint
    )


def _ctx():
    mongo = AsyncMongoMockClient()
    store = MongoCheckpointStore(mongo[DB_NAME])
    return ExtractContext(redis=fakeredis.aioredis.FakeRedis(), checkpoints=store), store


@pytest.mark.asyncio
async def test_min_id_checkpoint_advances_per_flush_and_at_end(monkeypatch):
    monkeypatch.setattr(extract_mod, "FLUSH_BATCH", 2)
    ctx, store = _ctx()
    saves = []
    real_save = store.save

    async def spy(source, state):
        saves.append(dict(state))
        await real_save(source, state)

    store.save = spy

    raws = [{"id": 10}, {"id": 11}, {"bad": True, "id": 99}, {"id": 12}, {"id": 13}]
    count = await run_extract(_spec(raws, MinIdCheckpoint("itms_min_id")), ctx)

    assert count == 4
    # Flush after ids 10,11 -> 12; after 12,13 -> 14; final save also 14.
    # The untransformable id 99 never advances the checkpoint.
    assert saves == [
        {"itms_min_id": "12"},
        {"itms_min_id": "14"},
        {"itms_min_id": "14"},
    ]
    assert ctx.state["itms_min_id"] == "14"


@pytest.mark.asyncio
async def test_min_id_resumes_from_stored_checkpoint():
    ctx, store = _ctx()
    await store.save("itms", {"itms_min_id": "50"})
    seen = []

    async def fetch(cycle):
        seen.append(cycle.cursor)
        return
        yield

    spec = SourceSpec(
        name="itms",
        settings=_Settings,
        fetch=fetch,
        transform=_notice,
        checkpoint=MinIdCheckpoint("itms_min_id"),
    )
    await run_extract(spec, ctx)

    assert seen == [50]
    # Nothing fetched: the checkpoint stays put rather than regressing.
    assert (await store.get("itms"))["itms_min_id"] == "50"


@pytest.mark.asyncio
async def test_wall_clock_checkpoint_not_saved_when_fetch_fails():
    ctx, store = _ctx()

    async def fetch(cycle):
        yield {"id": 1}
        raise RuntimeError("upstream down")

    spec = SourceSpec(
        name="crz",
        settings=_Settings,
        fetch=fetch,
        transform=_notice,
        checkpoint=WallClockCheckpoint("crz_since"),
    )
    with pytest.raises(RuntimeError):
        await run_extract(spec, ctx)

    assert "crz_since" not in (await store.get("crz") or {})


@pytest.mark.asyncio
async def test_max_modified_saves_newest_then_keeps_stored_when_none_seen():
    ctx, store = _ctx()
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 2, 1, tzinfo=UTC)
    checkpoint = MaxModifiedCheckpoint("vestnik_last_modified", historical=lambda s: False)

    await run_extract(
        _spec([{"id": 1, "modified": newer}, {"id": 2, "modified": older}], checkpoint, "vestnik"),
        ctx,
    )
    assert (await store.get("vestnik"))["vestnik_last_modified"] == newer.isoformat()

    # An empty cycle must keep the stored value, not erase it.
    await run_extract(_spec([], checkpoint, "vestnik"), ctx)
    assert (await store.get("vestnik"))["vestnik_last_modified"] == newer.isoformat()


@pytest.mark.asyncio
async def test_max_modified_historical_ignores_stored_checkpoint():
    ctx, store = _ctx()
    await store.save("vestnik", {"vestnik_last_modified": "2026-03-01T00:00:00+00:00"})
    seen = []

    async def fetch(cycle):
        seen.append(cycle.cursor)
        return
        yield

    spec = SourceSpec(
        name="vestnik",
        settings=_Settings,
        fetch=fetch,
        transform=_notice,
        checkpoint=MaxModifiedCheckpoint("vestnik_last_modified", historical=lambda s: True),
    )
    await run_extract(spec, ctx)

    assert seen == [None]
