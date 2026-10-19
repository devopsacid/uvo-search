"""Checkpoint arithmetic shared by the extractor workers."""

import logging
from datetime import UTC, date, datetime, timedelta

logger = logging.getLogger(__name__)


def resolve_since(stored: object, *, recent_days: int, now: datetime | None = None) -> date:
    """Parse a stored ISO checkpoint into a ``since`` date.

    Falls back to ``recent_days`` before ``now`` when the checkpoint is
    missing or unparseable (logged, never silently).
    """
    now = now or datetime.now(UTC)
    if stored:
        try:
            return datetime.fromisoformat(str(stored)).date()
        except (ValueError, TypeError):
            logger.warning("unparseable checkpoint %r; falling back to recent_days", stored)
    return (now - timedelta(days=recent_days)).date()


def next_checkpoint(cycle_start: datetime, *, overlap_seconds: int) -> str:
    """Checkpoint to persist after a successful cycle.

    Uses the cycle's *start* (not its end) minus an overlap: anything the
    source published or modified while the cycle was running — or that was
    still propagating through the upstream API — is re-fetched next time.
    Re-fetching is safe because ingestion is idempotent on content_hash.
    """
    return (cycle_start - timedelta(seconds=overlap_seconds)).isoformat()
