"""ITMS2014+ extractor — cursor-paginated async generator.

The list endpoint /v2/verejneObstaravania returns only reference stubs — it
does NOT include title (nazov), publication date, CPV code, or resolved
procurer name/ICO. To get those fields we fetch the singular procurement
detail /v2/verejneObstaravania/{id} (which carries title, date, and inline
zadavatel.subjekt ICO), plus the contracts list, plus the subject detail
/v2/subjekty/{id} for the procurer name (cached across procurements since
many share the same subject).

Contracts are enriched with supplier names via GET /v2/dodavatelia/{id}
because the contracts endpoint only embeds an id reference for the main
supplier — the name field requires a separate lookup.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from uvo_pipeline.cache import CacheBackend, MemoryCache
from uvo_pipeline.utils.http_retry import fetch_with_retry
from uvo_pipeline.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
_LIST_PATH = "/v2/verejneObstaravania"
_SUBJECT_PATH = "/v2/subjekty"
_SUPPLIER_PATH = "/v2/dodavatelia"

# A 404 is a stable answer, but cache it only briefly: records can appear later.
_NEGATIVE_CACHE_TTL_SECONDS = 3600


async def _fetch_by_id(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    path_prefix: str,
    id_: int,
    cache_backend: CacheBackend,
    key_prefix: str,
    cache_ttl_seconds: int,
) -> dict | None:
    """Fetch /{path_prefix}/{id_} via cache_backend.

    Returns None when the record is missing or could not be fetched. Only a
    definitive 404 is (briefly) negative-cached; transient failures (5xx,
    timeouts, connection errors) are retried and, if they persist, are NOT
    cached so the next lookup tries again instead of hiding the record for
    ``cache_ttl_seconds``.
    """
    key = f"{key_prefix}:{id_}"
    cached = await cache_backend.get(key)
    if cached is not None:
        return cached if cached else None
    await rate_limiter.acquire()
    try:
        resp = await fetch_with_retry(
            lambda: client.get(f"{path_prefix}/{id_}"), label=f"itms {path_prefix}/{id_}"
        )
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.warning("ITMS %s/%s fetch failed (not cached): %s", path_prefix, id_, exc)
        return None
    if resp.status_code == 404:
        await cache_backend.set(
            key, {}, ttl_seconds=min(cache_ttl_seconds, _NEGATIVE_CACHE_TTL_SECONDS)
        )
        return None
    if resp.status_code != 200:
        logger.warning(
            "ITMS %s/%s returned HTTP %s (not cached)", path_prefix, id_, resp.status_code
        )
        return None
    data = resp.json() or {}
    await cache_backend.set(key, data, ttl_seconds=cache_ttl_seconds)
    return data


async def _fetch_subject(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    subject_id: int,
    cache_backend: CacheBackend,
    cache_ttl_seconds: int,
) -> dict | None:
    """Resolve a subject by id, caching results across the run."""
    return await _fetch_by_id(
        client,
        rate_limiter,
        _SUBJECT_PATH,
        subject_id,
        cache_backend,
        "itms:subject",
        cache_ttl_seconds,
    )


def _extract_subject_id(item: dict) -> int | None:
    ref = (item.get("obstaravatelSubjekt") or {}).get("subjekt") or {}
    sid = ref.get("id")
    return int(sid) if sid is not None else None


async def fetch_procurements(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    *,
    min_id: int = 0,
    max_items: int | None = None,
    cache_backend: CacheBackend | None = None,
    cache_ttl_seconds: int = 7 * 24 * 3600,
) -> AsyncIterator[dict]:
    if cache_backend is None:
        cache_backend = MemoryCache()

    cursor = min_id
    yielded = 0

    while True:
        if max_items is not None and yielded >= max_items:
            return
        await rate_limiter.acquire()
        try:
            response = await fetch_with_retry(
                lambda: client.get(_LIST_PATH, params={"minId": cursor, "limit": 100}),
                label="itms list",
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("ITMS list HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
            raise
        except httpx.RequestError as exc:
            logger.error("ITMS list request failed: %s", exc)
            raise

        items = response.json()
        if not items:
            break

        for stub in items:
            pid = stub["id"]

            await rate_limiter.acquire()
            try:
                detail_resp = await fetch_with_retry(
                    lambda pid=pid: client.get(f"{_LIST_PATH}/{pid}"), label=f"itms detail {pid}"
                )
                item = detail_resp.json() if detail_resp.status_code == 200 else stub
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                logger.warning("ITMS detail failed id=%s: %s", pid, exc)
                item = stub

            await rate_limiter.acquire()
            try:
                contracts_resp = await fetch_with_retry(
                    lambda pid=pid: client.get(f"{_LIST_PATH}/{pid}/zmluvyVerejneObstaravanie"),
                    label=f"itms contracts {pid}",
                )
                item["_contracts"] = (
                    contracts_resp.json() if contracts_resp.status_code == 200 else []
                )
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                logger.warning("ITMS contracts failed id=%s: %s", pid, exc)
                item["_contracts"] = []

            # Enrich each contract with resolved supplier name (ICO is inline; name requires extra fetch)
            for contract in item["_contracts"]:
                hlavny = contract.get("hlavnyDodavatelDodavatelObstaravatel") or {}
                sup_id = hlavny.get("id")
                if sup_id is not None:
                    supplier = await _fetch_by_id(
                        client,
                        rate_limiter,
                        _SUPPLIER_PATH,
                        int(sup_id),
                        cache_backend,
                        "itms:supplier",
                        cache_ttl_seconds,
                    )
                    if supplier:
                        contract["_supplier"] = supplier

                # detail-endpoint shape may carry dodavatelia[] (multi-supplier)
                multi = contract.get("dodavatelia") or []
                if multi:
                    enriched = []
                    for entry in multi:
                        eid = entry.get("id")
                        if eid is not None:
                            s = await _fetch_by_id(
                                client,
                                rate_limiter,
                                _SUPPLIER_PATH,
                                int(eid),
                                cache_backend,
                                "itms:supplier",
                                cache_ttl_seconds,
                            )
                            enriched.append(s if s else entry)
                        else:
                            enriched.append(entry)
                    contract["_suppliers"] = enriched

            sid = _extract_subject_id(item)
            if sid is not None:
                subject = await _fetch_subject(
                    client, rate_limiter, sid, cache_backend, cache_ttl_seconds
                )
                if subject:
                    item["_subject"] = subject

            yield item
            yielded += 1
            if max_items is not None and yielded >= max_items:
                return

        cursor = max(item["id"] for item in items) + 1
