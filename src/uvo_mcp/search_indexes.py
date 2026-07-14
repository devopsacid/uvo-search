"""Atlas Search index definitions and idempotent provisioning."""

from __future__ import annotations

import logging
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
                    "procurer": {
                        "type": "document",
                        "fields": {"name": {"type": "string"}},
                    },
                    "awards": {
                        "type": "document",
                        "fields": {
                            "supplier": {
                                "type": "document",
                                "fields": {"name": {"type": "string"}},
                            }
                        },
                    },
                    "cpv_code": {"type": "token"},
                    "publication_date": {"type": "date"},
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


async def ensure_indexes(db) -> None:
    """Create each Atlas Search index if missing, or update it if the live
    definition has drifted from the code. Idempotent."""
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
        except Exception as exc:
            logger.warning("search index provisioning failed for %s: %s", coll, exc)
    await ensure_vector_indexes(db)


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
        except Exception:
            pass  # index already exists
