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
                    "title": {"type": "string"},
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


async def ensure_indexes(db) -> None:
    """Create each Atlas Search index if missing. Idempotent."""
    for coll, spec in INDEX_DEFINITIONS.items():
        try:
            existing = [i async for i in db[coll].list_search_indexes()]
            names = {i.get("name") for i in existing}
            if spec["name"] in names:
                logger.info("search index already present: %s.%s", coll, spec["name"])
                continue
            await db[coll].create_search_index(spec)
            logger.info("search index created: %s.%s", coll, spec["name"])
        except Exception as exc:
            logger.warning("search index provisioning failed for %s: %s", coll, exc)
