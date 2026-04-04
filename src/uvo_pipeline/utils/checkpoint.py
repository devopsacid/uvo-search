"""Checkpoint store — track last-run state per source in MongoDB."""

import logging
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


async def get_checkpoint(db: AsyncIOMotorDatabase, source: str) -> dict:
    """Return the stored checkpoint for a source, or empty dict if none."""
    doc = await db.pipeline_state.find_one({"source": source})
    return doc or {}


async def save_checkpoint(db: AsyncIOMotorDatabase, source: str, state: dict) -> None:
    """Upsert the checkpoint for a source."""
    await db.pipeline_state.update_one(
        {"source": source},
        {"$set": {**state, "source": source, "last_run_at": datetime.utcnow()}},
        upsert=True,
    )
    logger.debug("Checkpoint saved for source %s", source)
