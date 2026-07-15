"""CheckpointStore port adapter — wraps the pipeline_state collection.

Extracted so extractor workers can depend on the CheckpointStore port instead
of importing uvo_pipeline.utils.checkpoint directly (Phase 5 write-side).
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from uvo_pipeline.utils.checkpoint import get_checkpoint, save_checkpoint


class MongoCheckpointStore:
    """CheckpointStore port backed by the ``pipeline_state`` collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def get(self, source: str) -> dict:
        return await get_checkpoint(self._db, source)

    async def save(self, source: str, state: dict) -> None:
        await save_checkpoint(self._db, source, state)
