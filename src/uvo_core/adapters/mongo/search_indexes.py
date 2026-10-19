"""Atlas Search index definitions, idempotent provisioning and a readiness probe.

Single owner of search-index bootstrap: both the MCP and the API lifespans call
``ensure_indexes`` at startup, and both ``/readyz`` endpoints consult
``SearchIndexProbe`` so a pod whose required indexes are missing is not ready.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

_SK_ANALYZER = {
    "name": "sk_folding",
    "tokenizer": {"type": "standard"},
    "tokenFilters": [{"type": "lowercase"}, {"type": "icuFolding"}],
}

INDEX_DEFINITIONS: dict[str, dict[str, Any]] = {
    "procurers": {
        "name": "default",
        "definition": {
            "analyzers": [_SK_ANALYZER],
            "analyzer": "sk_folding",
            "searchAnalyzer": "sk_folding",
            "mappings": {
                "dynamic": False,
                "fields": {
                    "name": [
                        {"type": "string"},
                        {
                            "type": "autocomplete",
                            "tokenization": "edgeGram",
                            "minGrams": 2,
                            "maxGrams": 15,
                            "foldDiacritics": True,
                        },
                    ],
                    "ico": {"type": "token"},
                },
            },
        },
    },
    "suppliers": {
        "name": "default",
        "definition": {
            "analyzers": [_SK_ANALYZER],
            "analyzer": "sk_folding",
            "searchAnalyzer": "sk_folding",
            "mappings": {
                "dynamic": False,
                "fields": {
                    "name": [
                        {"type": "string"},
                        {
                            "type": "autocomplete",
                            "tokenization": "edgeGram",
                            "minGrams": 2,
                            "maxGrams": 15,
                            "foldDiacritics": True,
                        },
                    ],
                    "ico": {"type": "token"},
                },
            },
        },
    },
    "notices": {
        "name": "default",
        "definition": {
            "analyzers": [_SK_ANALYZER],
            "analyzer": "sk_folding",
            "searchAnalyzer": "sk_folding",
            "mappings": {
                "dynamic": False,
                "fields": {
                    "title": [
                        {"type": "string"},
                        {
                            "type": "autocomplete",
                            "tokenization": "edgeGram",
                            "minGrams": 2,
                            "maxGrams": 15,
                            "foldDiacritics": True,
                        },
                    ],
                    "description": {"type": "string"},
                    # token mappings below back the compound.filter clauses and
                    # $search.sort emitted by uvo_core.adapters.mongo.procurements.
                    # A filter on an unmapped path matches nothing, so adding a
                    # filter there means adding its mapping here (index rebuild).
                    "notice_type": {"type": "token"},
                    "procurer": {
                        "type": "document",
                        "fields": {
                            "name": {"type": "string"},
                            "ico": {"type": "token"},
                        },
                    },
                    "awards": {
                        "type": "document",
                        "fields": {
                            "supplier": {
                                "type": "document",
                                "fields": {
                                    "name": {"type": "string"},
                                    "ico": {"type": "token"},
                                },
                            }
                        },
                    },
                    "cpv_code": {"type": "token"},
                    # Stored as an ISO "YYYY-MM-DD" string (model_dump(mode="json")),
                    # which the `date` type does not index; `token` gives string
                    # range + sort. `date` is kept for any BSON-date legacy docs.
                    "publication_date": [{"type": "date"}, {"type": "token"}],
                },
            },
        },
    },
}


def definition_is_current(desired: Any, live: Any) -> bool:
    """True if every key/value in ``desired`` is present in ``live``.

    Atlas Search stores an enriched copy of each definition (adding
    ``indexOptions``/``store``/``norms``, reordering fields, defaulting
    ``dynamic``), so exact equality never holds against ``latestDefinition``.
    Instead we check that the definition we want is structurally contained in
    the live one. If it is not, the live index has drifted from the code and
    needs ``updateSearchIndex``. This is order-independent for the multi-mapping
    field lists (e.g. ``title`` = string + autocomplete).
    """
    if isinstance(desired, dict):
        if not isinstance(live, dict):
            return False
        return all(k in live and definition_is_current(v, live[k]) for k, v in desired.items())
    if isinstance(desired, list):
        if not isinstance(live, list):
            return False
        return all(any(definition_is_current(d, x) for x in live) for d in desired)
    return desired == live


async def _ensure_collections(db) -> None:
    """Create the indexed collections if absent.

    Atlas Search refuses ``createSearchIndex`` on a collection that does not exist,
    which is the state of a fresh database until the first ingest. Best effort and
    race-safe: a concurrent creator (the ingestor) just makes ``create_collection`` fail.
    """
    try:
        existing = set(await db.list_collection_names())
    except Exception as exc:  # noqa: BLE001
        logger.debug("list_collection_names failed: %s", exc)
        return
    for coll in INDEX_DEFINITIONS:
        if coll in existing:
            continue
        try:
            await db.create_collection(coll)
            logger.info("collection created for search index: %s", coll)
        except Exception as exc:  # noqa: BLE001 - already exists / lost a race
            logger.debug("create_collection skipped for %s: %s", coll, exc)


async def ensure_indexes(db) -> bool:
    """Create each Atlas Search index if missing, or update it if the live
    definition has drifted from the code. Idempotent.

    Returns ``True`` when every collection was processed without error and
    ``False`` otherwise (failures are logged at ERROR) so callers can retry.
    """
    ok = True
    await _ensure_collections(db)
    for coll, spec in INDEX_DEFINITIONS.items():
        try:
            existing = [i async for i in db[coll].list_search_indexes()]
            current = next((i for i in existing if i.get("name") == spec["name"]), None)
            if current is None:
                await db[coll].create_search_index(spec)
                logger.info("search index created: %s.%s", coll, spec["name"])
                continue
            live_def = current.get("latestDefinition") or current.get("definition") or {}
            if definition_is_current(spec["definition"], live_def):
                logger.info("search index up to date: %s.%s", coll, spec["name"])
                continue
            await db[coll].update_search_index(spec["name"], spec["definition"])
            logger.info(
                "search index definition drifted; updateSearchIndex issued (async rebuild): %s.%s",
                coll,
                spec["name"],
            )
        except Exception as exc:  # noqa: BLE001 - keep provisioning the other collections
            ok = False
            logger.error("search index provisioning failed for %s: %s", coll, exc)
    await ensure_vector_indexes(db)
    return ok


async def retry_ensure_indexes(
    db,
    *,
    ensure: Callable[[Any], Awaitable[Any]] | None = None,
    interval: float = 30.0,
    max_interval: float = 300.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Re-run provisioning with exponential backoff until it succeeds.

    Meant to run as a background task after a failed first attempt (fresh DB, mongot
    still starting). Returns on the first success; cancel it on shutdown. Each failed
    attempt is logged at WARNING.
    """
    run = ensure or ensure_indexes
    delay = interval
    while True:
        await sleep(delay)
        try:
            ok = await run(db) is not False
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep retrying
            logger.warning("search index provisioning retry failed: %s", exc)
            ok = False
        else:
            if not ok:
                logger.warning("search index provisioning incomplete; retrying in %.0fs", delay)
        if ok:
            logger.info("search index provisioning succeeded on retry")
            return
        delay = min(delay * 2, max_interval)


async def ensure_vector_indexes(db) -> None:
    for coll in ("procurers", "suppliers"):
        try:
            await db.command(
                "createSearchIndexes",
                coll,
                indexes=[
                    {
                        "name": "vector_index",
                        "type": "vectorSearch",
                        "definition": {
                            "fields": [
                                {
                                    "type": "vector",
                                    "path": "name_embedding",
                                    "numDimensions": 384,
                                    "similarity": "cosine",
                                }
                            ]
                        },
                    }
                ],
            )
        except Exception as exc:  # noqa: BLE001
            # Usually "index already exists"; a real failure surfaces via the
            # readiness probe (required text indexes) and query errors.
            logger.debug("vector index create skipped for %s: %s", coll, exc)


REQUIRED_SEARCH_INDEXES: tuple[tuple[str, str], ...] = tuple(
    (coll, spec["name"]) for coll, spec in INDEX_DEFINITIONS.items()
)


async def missing_search_indexes(db) -> list[str]:
    """``collection.index`` labels of required search indexes that are absent or not queryable."""
    missing: list[str] = []
    for coll, name in REQUIRED_SEARCH_INDEXES:
        label = f"{coll}.{name}"
        try:
            existing = [i async for i in db[coll].list_search_indexes()]
        except Exception as exc:  # noqa: BLE001 - unreachable server => not ready
            logger.warning("search index check failed for %s: %s", coll, exc)
            missing.append(label)
            continue
        current = next((i for i in existing if i.get("name") == name), None)
        if current is None or current.get("queryable") is False:
            missing.append(label)
    return missing


class SearchIndexProbe:
    """Readiness check for the required search indexes, cached for ``ttl`` seconds.

    ``/readyz`` is hit every few seconds by the kubelet; listing search indexes
    on every probe would be needless load, so the result is reused briefly.
    """

    def __init__(self, ttl: float = 30.0, clock=time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._checked_at: float | None = None
        self._missing: list[str] = []

    async def missing(self, db) -> list[str]:
        now = self._clock()
        if self._checked_at is not None and now - self._checked_at < self._ttl:
            return list(self._missing)
        self._missing = await missing_search_indexes(db)
        self._checked_at = now
        if self._missing:
            logger.error("readiness: required search indexes missing: %s", self._missing)
        return list(self._missing)

    async def ready(self, db) -> bool:
        return not await self.missing(db)
