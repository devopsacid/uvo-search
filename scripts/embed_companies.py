"""Backfill: generate name_embedding for all procurers and suppliers."""

import asyncio

from fastembed import TextEmbedding
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

from uvo_mcp.config import Settings


async def embed_collection(coll, model, batch_size: int = 256) -> None:
    total = await coll.count_documents({"name_embedding": {"$exists": False}})
    print(f"  {coll.name}: {total} documents to embed", flush=True)
    if not total:
        return

    done = 0
    ids, texts = [], []

    async for doc in coll.find({"name_embedding": {"$exists": False}}, {"_id": 1, "name": 1}):
        ids.append(doc["_id"])
        texts.append(doc.get("name") or "")
        if len(ids) >= batch_size:
            vecs = list(model.embed(texts))
            await coll.bulk_write([
                UpdateOne({"_id": oid}, {"$set": {"name_embedding": vec.tolist()}})
                for oid, vec in zip(ids, vecs)
            ], ordered=False)
            done += len(ids)
            print(f"  {coll.name}: {done}/{total}", end="\r", flush=True)
            ids, texts = [], []

    if ids:
        vecs = list(model.embed(texts))
        await coll.bulk_write([
            UpdateOne({"_id": oid}, {"$set": {"name_embedding": vec.tolist()}})
            for oid, vec in zip(ids, vecs)
        ], ordered=False)
        done += len(ids)

    print(f"  {coll.name}: {done} done        ", flush=True)


async def main() -> None:
    settings = Settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]
    model = TextEmbedding("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    print("Model loaded. Embedding companies...")
    for name in ("procurers", "suppliers"):
        await embed_collection(db[name], model)
    print("Done.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
