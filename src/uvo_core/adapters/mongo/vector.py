"""Vector search over company name embeddings ($vectorSearch)."""


async def vsearch(db, collection: str, vector: list[float], limit: int) -> list[dict]:
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "name_embedding",
                "queryVector": vector,
                "numCandidates": max(limit * 10, 100),
                "limit": limit,
            }
        },
        {"$project": {"_id": 1, "ico": 1, "name": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]
    rows = await db[collection].aggregate(pipeline).to_list(limit)
    for r in rows:
        r["_id"] = str(r["_id"])
    return rows
