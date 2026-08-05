"""Translate user query strings into Atlas $search stage fragments."""

from __future__ import annotations

# Minimum literal characters required before the first wildcard metacharacter.
# Below this, Atlas must walk a prohibitively large share of the term
# dictionary across every analyzed path, which is a cheap DoS primitive on
# an unauthenticated endpoint.
_MIN_WILDCARD_PREFIX = 3


def _wildcard_prefix_len(q: str) -> int:
    """Number of literal characters before the first * or ? in the query."""
    candidates = [i for i in (q.find("*"), q.find("?")) if i != -1]
    return min(candidates) if candidates else len(q)


def build_search_stage(query: str, path: list[str]) -> dict:
    """Return the operator body for a $search stage (without the index key).

    Empty string → list-all via `exists`.
    "quoted phrase" → `phrase` operator.
    Contains * or ? → `wildcard` operator.
    Otherwise → compound: phrase (3× boost) + fuzzy text (maxEdits 1-2) + autocomplete prefix.
    """
    q = query.strip()
    if not q:
        return {"exists": {"path": path[0]}}

    if len(q) >= 2 and q.startswith('"') and q.endswith('"'):
        return {"phrase": {"query": q[1:-1], "path": path}}

    if ("*" in q or "?" in q) and _wildcard_prefix_len(q) >= _MIN_WILDCARD_PREFIX:
        return {
            "wildcard": {
                "query": q,
                "path": path,
                "allowAnalyzedField": True,
            }
        }

    max_edits = 2 if len(q) >= 6 else 1
    return {
        "compound": {
            "should": [
                # Phrase match scores highest when all words appear in order
                {
                    "phrase": {
                        "query": q,
                        "path": path,
                        "score": {"boost": {"value": 3}},
                    }
                },
                # Fuzzy text — tolerates typos across the full string
                {
                    "text": {
                        "query": q,
                        "path": path,
                        "fuzzy": {"maxEdits": max_edits},
                    }
                },
                # Autocomplete prefix — still useful for short / in-progress queries
                {
                    "autocomplete": {
                        "query": q,
                        "path": path[0],
                        "fuzzy": {"maxEdits": 1},
                    }
                },
            ]
        }
    }
