"""Declarative extractor: a ``SourceSpec`` plus one generic cycle loop.

A source module supplies only what is genuinely source-specific - how to
fetch raw records, how to transform one, and which checkpoint strategy
governs its resume point. ``run_extract`` owns everything else: checkpoint
load, fetch, transform, hash, buffer, flush (backpressure + XADD) and
checkpoint save.

Checkpoint semantics per source (do not unify - they differ on purpose):

* ``WallClockCheckpoint`` (CRZ, TED): resume from cycle start minus an
  overlap; saved once at the end of a fully successful cycle.
* ``MaxModifiedCheckpoint`` (Vestnik): resume from the newest dataset
  ``modified`` seen (a source-side timestamp, so no overlap); saved at the end.
* ``MinIdCheckpoint`` (ITMS): resume from the highest id seen + 1; saved after
  every flush as well as at the end, so a crash loses only the partial buffer.
"""

import logging
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import redis.asyncio

from uvo_core.adapters.redis.notice_stream import RedisNoticeStream
from uvo_core.domain.hashing import compute_notice_hash
from uvo_core.domain.models import CanonicalNotice
from uvo_pipeline.config import PipelineSettings, get_pipeline_settings
from uvo_workers.checkpoints import next_checkpoint, resolve_since
from uvo_workers.flush import flush_notices
from uvo_workers.runner import run_extractor_loop
from uvo_workers.settings import ExtractorSettings

logger = logging.getLogger(__name__)

FLUSH_BATCH = 500


class CheckpointStore(Protocol):
    async def get(self, source: str) -> dict: ...

    async def save(self, source: str, state: dict) -> None: ...


@dataclass
class ExtractContext:
    """Injected collaborators for one cycle (tests pass fakes)."""

    redis: redis.asyncio.Redis
    checkpoints: CheckpointStore
    # Process-lifetime scratch shared across cycles (ITMS keeps its last min_id here).
    state: dict = field(default_factory=dict)

    @classmethod
    def from_loop_state(cls, redis_client: redis.asyncio.Redis, state: dict) -> "ExtractContext":
        """Adapt the ``(redis, state)`` call made by ``run_extractor_loop``."""
        return cls(redis=redis_client, checkpoints=state["_checkpoint_store"], state=state)


@dataclass
class Cycle:
    """Everything a fetch/transform/checkpoint callback may need for one cycle."""

    settings: ExtractorSettings
    pipeline: PipelineSettings
    redis: redis.asyncio.Redis
    run_id: str
    started_at: datetime
    state: dict
    # Resume point computed by the checkpoint strategy (a date, an int id, or None).
    cursor: Any = None
    # Strategy-private progress written by fetch/on_item (e.g. max id seen).
    progress: dict = field(default_factory=dict)


class CheckpointStrategy(Protocol):
    cursor_name: str

    def cursor(self, stored: dict, cycle: Cycle) -> Any: ...

    def on_item(self, cycle: Cycle, raw: Any) -> None:
        """Called after ``raw`` transformed successfully."""

    def flush_state(self, cycle: Cycle) -> dict | None:
        """State to persist right after a mid-cycle flush, or None."""

    def final_state(self, cycle: Cycle) -> dict | None:
        """State to persist after a successful cycle, or None to skip saving."""


class WallClockCheckpoint:
    """Cycle start minus overlap (CRZ, TED)."""

    cursor_name = "since"

    def __init__(self, key: str) -> None:
        self.key = key

    def cursor(self, stored: dict, cycle: Cycle):
        return resolve_since(
            stored.get(self.key),
            recent_days=cycle.pipeline.recent_days,
            now=cycle.started_at,
        )

    def on_item(self, cycle: Cycle, raw: Any) -> None:
        pass

    def flush_state(self, cycle: Cycle) -> dict | None:
        return None

    def final_state(self, cycle: Cycle) -> dict | None:
        return {
            self.key: next_checkpoint(
                cycle.started_at, overlap_seconds=cycle.settings.checkpoint_overlap_seconds
            )
        }


class MaxModifiedCheckpoint:
    """Newest dataset ``modified`` seen (Vestnik).

    The fetch callback reports each dataset via ``observe``. ``historical``
    ignores any stored checkpoint and fetches everything.
    """

    cursor_name = "since"
    _MAX = "max_modified"

    def __init__(self, key: str, *, historical: Callable[[ExtractorSettings], bool]) -> None:
        self.key = key
        self._historical = historical

    def cursor(self, stored: dict, cycle: Cycle):
        cycle.progress["stored"] = stored.get(self.key)
        if self._historical(cycle.settings):
            return None
        # The checkpoint is a source-side timestamp, so no overlap is needed.
        return resolve_since(
            stored.get(self.key),
            recent_days=cycle.pipeline.recent_days,
            now=datetime.now(UTC),
        )

    @classmethod
    def observe(cls, cycle: Cycle, modified: datetime | None) -> None:
        current = cycle.progress.get(cls._MAX)
        if modified and (current is None or modified > current):
            cycle.progress[cls._MAX] = modified

    def on_item(self, cycle: Cycle, raw: Any) -> None:
        pass

    def flush_state(self, cycle: Cycle) -> dict | None:
        return None

    def final_state(self, cycle: Cycle) -> dict | None:
        newest = cycle.progress.get(self._MAX)
        if newest is not None:
            return {self.key: newest.isoformat()}
        if cycle.progress.get("stored"):
            return {self.key: cycle.progress["stored"]}
        return None


class MinIdCheckpoint:
    """Highest numeric id seen + 1, persisted per flush (ITMS)."""

    cursor_name = "min_id"
    _MAX = "max_seen"

    def __init__(self, key: str) -> None:
        self.key = key

    def cursor(self, stored: dict, cycle: Cycle) -> int:
        min_id = int(stored.get(self.key) or cycle.state.get(self.key) or 0)
        cycle.progress[self._MAX] = min_id - 1
        return min_id

    def on_item(self, cycle: Cycle, raw: Any) -> None:
        cycle.progress[self._MAX] = max(cycle.progress[self._MAX], int(raw["id"]))

    def _state(self, cycle: Cycle) -> dict:
        value = str(cycle.progress[self._MAX] + 1)
        cycle.state[self.key] = value
        return {self.key: value}

    def flush_state(self, cycle: Cycle) -> dict | None:
        return self._state(cycle)

    def final_state(self, cycle: Cycle) -> dict | None:
        return self._state(cycle)


@dataclass(frozen=True)
class SourceSpec:
    name: str
    settings: Callable[[], ExtractorSettings]
    # Async generator of raw records; owns its HTTP clients and rate limiting.
    fetch: Callable[[Cycle], AsyncIterator[Any]]
    transform: Callable[[Any], CanonicalNotice]
    checkpoint: CheckpointStrategy


def _raw_id(raw: Any) -> Any:
    return raw.get("id") if isinstance(raw, dict) else None


async def run_extract(spec: SourceSpec, ctx: ExtractContext) -> int:
    """Run one extraction cycle for ``spec`` and return the notices XADDed."""
    settings = spec.settings()
    cycle = Cycle(
        settings=settings,
        pipeline=get_pipeline_settings(),
        redis=ctx.redis,
        run_id=uuid.uuid4().hex,
        started_at=datetime.now(UTC),
        state=ctx.state,
    )
    stream = RedisNoticeStream(ctx.redis, spec.name, maxlen=settings.stream_maxlen_approx)

    cycle.cursor = spec.checkpoint.cursor(await ctx.checkpoints.get(spec.name), cycle)
    logger.info("%s: extracting %s=%s", spec.name, spec.checkpoint.cursor_name, cycle.cursor)

    count = 0
    buffer: list[CanonicalNotice] = []
    async for raw in spec.fetch(cycle):
        try:
            notice = spec.transform(raw)
            notice.pipeline_run_id = cycle.run_id
            notice.content_hash = compute_notice_hash(notice)
            buffer.append(notice)
            spec.checkpoint.on_item(cycle, raw)
        except Exception as exc:
            logger.warning("%s transform error (id=%s): %s", spec.name, _raw_id(raw), exc)

        if len(buffer) >= FLUSH_BATCH:
            count += await flush_notices(stream, buffer, high_water=settings.stream_high_water)
            buffer.clear()
            state = spec.checkpoint.flush_state(cycle)
            if state:
                await ctx.checkpoints.save(spec.name, state)

    count += await flush_notices(stream, buffer, high_water=settings.stream_high_water)
    buffer.clear()

    state = spec.checkpoint.final_state(cycle)
    if state:
        await ctx.checkpoints.save(spec.name, state)
    return count


async def run_source(spec: SourceSpec) -> None:
    """Process entrypoint shared by ``python -m uvo_workers.<source>``."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = spec.settings()

    async def extract(redis_client: redis.asyncio.Redis, state: dict) -> int:
        return await run_extract(spec, ExtractContext.from_loop_state(redis_client, state))

    await run_extractor_loop(
        source=spec.name,
        interval_seconds=settings.interval_seconds,
        extract=extract,
        health_port=settings.health_port,
    )
