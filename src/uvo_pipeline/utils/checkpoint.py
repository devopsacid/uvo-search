"""Checkpoint store — track last-run state per source in MongoDB."""

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


async def get_checkpoint(db: AsyncIOMotorDatabase, source: str) -> dict:
    """Return the stored checkpoint for a source, or empty dict if none."""
    doc = await db.pipeline_state.find_one({"source": source})
    return doc or {}


async def save_checkpoint(db: AsyncIOMotorDatabase, source: str, state: dict) -> None:
    """Upsert the checkpoint for a source.

    Stamps `last_run_at` only when the caller passes it in `state`. Earlier
    versions auto-stamped on every save, which let a partial run (e.g. one
    that persisted Vestník but never finished CRZ) advance the next run's
    `from_date` past data that was never actually fetched. The orchestrator
    now sets `last_run_at` itself, only on the final pipeline-wide save.
    """
    await db.pipeline_state.update_one(
        {"source": source},
        {"$set": {**state, "source": source}},
        upsert=True,
    )
    logger.debug("Checkpoint saved for source %s", source)
