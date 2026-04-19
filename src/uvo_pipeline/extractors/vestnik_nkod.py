"""Vestník NKOD extractor — download and unpack bulletin JSON from dataset URLs."""

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import AsyncIterator

import httpx

from uvo_pipeline.catalog.nkod import VestnikDataset
from uvo_pipeline.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def _cache_key(url: str) -> str:
    segment = url.rstrip("/").split("/")[-1].split("?")[0]
    if segment:
        return segment
    return hashlib.sha1(url.encode()).hexdigest()


async def fetch_bulletin(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    dataset: VestnikDataset,
    *,
    cache_dir: Path | None = None,
) -> AsyncIterator[dict]:
    key = _cache_key(dataset.download_url)
    cache_path = cache_dir / "vestnik" / f"{key}.json" if cache_dir else None

    if cache_path and cache_path.exists():
        try:
            envelope = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("vestnik cache read failed %s: %s", cache_path, exc)
            envelope = None
    else:
        await rate_limiter.acquire()
        try:
            response = await client.get(dataset.download_url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "vestnik fetch HTTP %s %s: %s",
                exc.response.status_code,
                dataset.download_url,
                exc.response.text[:200],
            )
            return
        except httpx.RequestError as exc:
            logger.warning("vestnik fetch failed %s: %s", dataset.download_url, exc)
            return

        try:
            envelope = response.json()
        except Exception as exc:
            logger.warning("vestnik JSON decode failed %s: %s", dataset.download_url, exc)
            return

        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=cache_path.parent,
                    delete=False,
                    suffix=".tmp",
                ) as tmp:
                    json.dump(envelope, tmp)
                    tmp_path = Path(tmp.name)
                tmp_path.replace(cache_path)
            except Exception as exc:
                logger.warning("vestnik cache write failed %s: %s", cache_path, exc)

    items = envelope.get("bulletinItemList") if isinstance(envelope, dict) else None
    if items is None:
        logger.warning("vestnik envelope missing bulletinItemList: %s", dataset.download_url)
        return

    for idx, item in enumerate(items):
        try:
            raw = json.loads(item["itemData"])
        except Exception as exc:
            logger.warning("vestnik itemData parse failed idx=%d: %s", idx, exc)
            continue

        raw["_bulletin_year"] = envelope.get("year")
        raw["_bulletin_number"] = envelope.get("number")
        raw["_bulletin_publish_date"] = envelope.get("bulletinPublishDate")
        raw["_dataset_uri"] = dataset.uri
        raw["_dataset_title"] = dataset.title
        yield raw
