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

import logging
from collections.abc import AsyncIterator

import httpx

from uvo_pipeline.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
_LIST_PATH = "/v2/verejneObstaravania"
_SUBJECT_PATH = "/v2/subjekty"
_SUPPLIER_PATH = "/v2/dodavatelia"


async def _fetch_by_id(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    path_prefix: str,
    id_: int,
    cache: dict[int, dict],
) -> dict | None:
    """Fetch /{path_prefix}/{id_}, caching results; returns {} on 404/error."""
    if id_ in cache:
        return cache[id_]
    await rate_limiter.acquire()
    try:
        resp = await client.get(f"{path_prefix}/{id_}")
        if resp.status_code != 200:
            cache[id_] = {}
            return None
        data = resp.json() or {}
    except httpx.RequestError as exc:
        logger.warning("ITMS %s/%s fetch failed: %s", path_prefix, id_, exc)
        cache[id_] = {}
        return None
    cache[id_] = data
    return data


async def _fetch_subject(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    subject_id: int,
    cache: dict[int, dict],
) -> dict | None:
    """Resolve a subject by id, caching results across the run."""
    return await _fetch_by_id(client, rate_limiter, _SUBJECT_PATH, subject_id, cache)


def _extract_subject_id(item: dict) -> int | None:
    ref = (item.get("obstaravatelSubjekt") or {}).get("subjekt") or {}
    sid = ref.get("id")
    return int(sid) if sid is not None else None


async def fetch_procurements(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    *,
    min_id: int = 0,
) -> AsyncIterator[dict]:
    cursor = min_id
    subject_cache: dict[int, dict] = {}
    supplier_cache: dict[int, dict] = {}

    while True:
        await rate_limiter.acquire()
        try:
            response = await client.get(_LIST_PATH, params={"minId": cursor, "limit": 100})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("ITMS list HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
            return
        except httpx.RequestError as exc:
            logger.error("ITMS list request failed: %s", exc)
            return

        items = response.json()
        if not items:
            break

        for stub in items:
            pid = stub["id"]

            await rate_limiter.acquire()
            try:
                detail_resp = await client.get(f"{_LIST_PATH}/{pid}")
                item = detail_resp.json() if detail_resp.status_code == 200 else stub
            except httpx.RequestError as exc:
                logger.warning("ITMS detail failed id=%s: %s", pid, exc)
                item = stub

            await rate_limiter.acquire()
            try:
                contracts_resp = await client.get(f"{_LIST_PATH}/{pid}/zmluvyVerejneObstaravanie")
                item["_contracts"] = (
                    contracts_resp.json() if contracts_resp.status_code == 200 else []
                )
            except httpx.RequestError as exc:
                logger.warning("ITMS contracts failed id=%s: %s", pid, exc)
                item["_contracts"] = []

            # Enrich each contract with resolved supplier name (ICO is inline; name requires extra fetch)
            for contract in item["_contracts"]:
                hlavny = contract.get("hlavnyDodavatelDodavatelObstaravatel") or {}
                sup_id = hlavny.get("id")
                if sup_id is not None:
                    supplier = await _fetch_by_id(
                        client, rate_limiter, _SUPPLIER_PATH, int(sup_id), supplier_cache
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
                                client, rate_limiter, _SUPPLIER_PATH, int(eid), supplier_cache
                            )
                            enriched.append(s if s else entry)
                        else:
                            enriched.append(entry)
                    contract["_suppliers"] = enriched

            sid = _extract_subject_id(item)
            if sid is not None:
                subject = await _fetch_subject(client, rate_limiter, sid, subject_cache)
                if subject:
                    item["_subject"] = subject

            yield item

        cursor = max(item["id"] for item in items) + 1
