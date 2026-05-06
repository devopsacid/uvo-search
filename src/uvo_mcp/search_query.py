"""Translate user query strings into Atlas $search stage fragments."""

from __future__ import annotations


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

    if "*" in q or "?" in q:
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
