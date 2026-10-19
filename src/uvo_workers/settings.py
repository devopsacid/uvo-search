"""Shared settings bases for the long-lived workers.

Env var names are the field names (no prefix), so every field a subclass
declares is also a deployment contract: compose and k8s set them verbatim.
Subclasses add only their own fields (e.g. ``crz_interval_seconds``) or
override a default (``health_port``).
"""

from collections.abc import Callable
from functools import lru_cache

from pydantic_settings import BaseSettings


class WorkerSettings(BaseSettings):
    """Fields every worker process has."""

    health_port: int = 8090

    model_config = {"env_file": ".env", "secrets_dir": "/run/secrets", "extra": "ignore"}


class ExtractorSettings(WorkerSettings):
    """Fields shared by the four source extractors."""

    # MAXLEN is only a memory safety net; backpressure (stream_high_water)
    # keeps the consumer-group backlog far below it so unread entries are
    # never trimmed.
    stream_maxlen_approx: int = 1_000_000
    stream_high_water: int = 50_000
    # Re-fetch this much history on every cycle so late-published or
    # still-propagating records are not skipped (ingestion is idempotent).
    # Only the wall-clock checkpoint strategy reads it.
    checkpoint_overlap_seconds: int = 86_400

    @property
    def interval_seconds(self) -> int:
        """Cycle interval; each source maps its own ``<source>_interval_seconds``."""
        raise NotImplementedError


def settings_factory[S: BaseSettings](cls: type[S]) -> Callable[[], S]:
    """One construction per process (cached factory idiom)."""
    return lru_cache(maxsize=None)(cls)
