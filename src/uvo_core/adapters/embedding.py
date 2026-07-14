"""FastEmbed wrapper — loads the multilingual model, degrades to None when unavailable."""

import asyncio
import logging
from typing import Any

from uvo_core.cache import _make_key, async_ttl_cache

logger = logging.getLogger(__name__)

_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def load_embedder() -> Any | None:
    """Return a loaded FastEmbed TextEmbedding, or None if fastembed is unavailable.

    Mirrors the previous lifespan behaviour: any import/load failure degrades the
    vector-search path instead of crashing the process.
    """
    try:
        from fastembed import TextEmbedding

        model = TextEmbedding(_MODEL_NAME)
        logger.info("FastEmbed model loaded")
        return model
    except Exception as exc:  # noqa: BLE001
        logger.warning("FastEmbed unavailable: %s", exc)
        return None


@async_ttl_cache(
    maxsize=512,
    ttl=300,
    key_from=lambda model, text: _make_key((text,), {}),
)
async def embed(model, text: str) -> list[float]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: list(next(model.embed([text]))))
