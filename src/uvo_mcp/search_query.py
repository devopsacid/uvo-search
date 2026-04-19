"""Translate user query strings into Atlas $search stage fragments."""

from __future__ import annotations


def build_search_stage(query: str, path: list[str]) -> dict:
    """Return the operator body for a $search stage (without the index key).

    Empty string → list-all via `exists`.
    "quoted phrase" → `phrase` operator.
    Contains * or ? → `wildcard` operator.
    Otherwise → compound of `autocomplete` (fuzzy=1) and `text`.
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

    return {
        "compound": {
            "should": [
                {
                    "autocomplete": {
                        "query": q,
                        "path": path[0],
                        "fuzzy": {"maxEdits": 1},
                    }
                },
                {"text": {"query": q, "path": path}},
            ]
        }
    }
