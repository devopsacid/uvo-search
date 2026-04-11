# Design: ITMS2014+ API Integration

**Date:** 2026-04-11
**Status:** Approved
**Source:** opendata.itms2014.sk (Information and Monitoring System for EU Structural Funds 2014+)

---

## Context

ITMS2014+ is the Slovak government's official open data API for EU Structural Funds (ESIF 2014–2020) projects and procurements. It is a fully public, unauthenticated REST/JSON API with Swagger docs at `https://opendata.itms2014.sk/swagger/?url=/v2/swagger.json`.

This integration complements the uvo.gov.sk scraper by providing rich structured data for EU-funded procurements — which represent a significant share of Slovak public spending. Unlike the scraper, this source requires no HTML parsing, no anti-bot handling, and no rate-limit gymnastics.

---

## Scope

- All procurements from the ITMS2014+ database (EU-funded, 2014–present)
- Procurement detail including contracts, procurer, suppliers, CPV, value
- Incremental updates via cursor-based pagination (`minId`)
- Full backfill on first run; incremental on subsequent runs

Out of scope: project financial data (`/v2/projekty`), accounting documents, operational programme details.

---

## Architecture

```
opendata.itms2014.sk REST API
      │
      ▼
extractors/itms.py         async generator — cursor-paginated, yields raw dicts
      │  yields raw dicts
      ▼
transformers/itms.py       transform_procurement(raw) → CanonicalNotice
      │
      ▼
orchestrator.py            Step N+1 (after UVO) — wired into run()
      │
      ▼
MongoDB + Neo4j loaders    same as all other sources
```

New files:
- `src/uvo_pipeline/extractors/itms.py`
- `src/uvo_pipeline/transformers/itms.py`

Modified files:
- `src/uvo_pipeline/config.py` — 2 new settings
- `src/uvo_pipeline/orchestrator.py` — new extraction step + checkpoint
- `src/uvo_pipeline/models.py` — add `"itms"` to `CanonicalNotice.source` Literal

Test files:
- `tests/pipeline/extractors/test_itms.py`
- `tests/pipeline/transformers/test_itms.py`

---

## Extractor: `extractors/itms.py`

### Public interface

```python
async def fetch_procurements(
    client: httpx.AsyncClient,
    rate_limiter: AsyncLimiter,
    *,
    min_id: int = 0,
    max_id: int | None = None,
) -> AsyncIterator[dict]
```

### Pagination

The API uses cursor-based pagination via `minId` parameter:

```
GET /v2/verejneObstaravania?minId={cursor}&limit=100
```

Response is a JSON array. When the array is empty or shorter than `limit`, iteration stops. The cursor for the next page is `max(item["id"] for item in page) + 1`.

Checkpoint stores the highest `id` seen so far, enabling incremental runs without re-fetching old records.

### Detail fetch

Each list item from `/v2/verejneObstaravania` contains enough fields for the canonical model. However, contract (award) data requires a secondary call:

```
GET /v2/verejneObstaravania/{id}/zmluvyVerejneObstaravanie
```

This returns an array of contracts linked to the procurement, each with supplier ICO, final value, and currency.

Detail fetch is skipped for procurements already in MongoDB (`source="itms"`, `source_id` match).

### Rate limiting

No published rate limit. Default: 5 req/s (more relaxed than the scraper — this is a purpose-built API). Shared `AsyncLimiter` pattern.

### Error handling

- HTTP 429: backoff + retry (max 3)
- HTTP 404 on detail: log debug, treat as no contracts
- Parse/validation errors: log warning, skip record, continue

---

## Transformer: `transformers/itms.py`

```python
def transform_procurement(raw: dict) -> CanonicalNotice
```

### Field mapping

| ITMS field | Canonical field | Notes |
|---|---|---|
| `id` | `source_id` | String(int) |
| `"itms"` | `source` | Literal |
| `nazov` | `title` | Slovak title |
| `datumZverejneniaVoVestniku` | `published_date` | ISO datetime → date |
| `hlavnyPredmetHlavnySlovnik.kod` | `cpv_codes[0]` | CPV code string |
| `predpokladanaHodnotaZakazky` | `estimated_value` | Float or None |
| `stav` | `status` | Mapped (see below) |
| `druhZakazky` | `notice_type` | Mapped (see below) |
| `obstaravatelSubjekt.nazov` | `procurer.name` | |
| `obstaravatelSubjekt.ico` | `procurer.ico` | |
| contracts array | `awards[]` | From secondary call |

### Status mapping

| ITMS `stav` | Canonical status |
|---|---|
| `Ukoncene` | `awarded` |
| `Zrusene` | `cancelled` |
| `Prebieha` | `active` |
| anything else | `unknown` |

### Notice type mapping

| ITMS `druhZakazky` | Canonical type |
|---|---|
| `Tovary` / `Sluzby` / `Stavebne prace` | `contract_notice` (pre-award) or `contract_award` (post-award, based on stav) |
| anything else | `other` |

Note: ITMS does not distinguish notice type the same way UVO/TED do. A procurement with `stav=Ukoncene` and contracts is treated as `contract_award`; otherwise `contract_notice`.

### Award mapping (from contracts)

Each contract in `zmluvyVerejneObstaravanie`:

| Contract field | Canonical field |
|---|---|
| `dodavatel.nazov` | `supplier.name` |
| `dodavatel.ico` | `supplier.ico` |
| `celkovaHodnotaZmluvy` | `award.value` |
| `mena` | `award.currency` |

---

## Orchestrator wiring

```python
# Step N+1 — ITMS2014+
itms_min_id = int(checkpoint.get("itms_min_id") or 0)
async for raw in fetch_procurements(client, rate_limiter, min_id=itms_min_id):
    notice = transform_procurement(raw)
    batch.append(notice)
    itms_min_id = max(itms_min_id, int(raw["id"]))
checkpoint["itms_min_id"] = str(itms_min_id)
```

No date-based mode distinction needed — cursor pagination is inherently incremental. Historical mode simply starts with `min_id=0`.

---

## Config additions (`config.py`)

```python
itms_base_url: str = "https://opendata.itms2014.sk"
itms_rate_limit: float = 5.0    # max requests per second
```

Both overridable via environment variables (`ITMS_BASE_URL`, `ITMS_RATE_LIMIT`).

---

## Models change

Add `"itms"` to the `source` Literal in `CanonicalNotice`:

```python
source: Literal["crz", "itms", "ted", "uvo", "vestnik"]
```

---

## Testing

### `tests/pipeline/extractors/test_itms.py`

- `test_fetch_yields_procurements` — mock one page of results, assert raw dicts yielded
- `test_fetch_cursor_pagination` — two pages, assert cursor increments correctly
- `test_fetch_stops_on_empty_page` — empty array response stops generator
- `test_fetch_contract_detail` — mock contract endpoint, assert award data in raw
- `test_fetch_skips_detail_for_existing` — mock MongoDB hit, assert no contract call
- `test_fetch_retries_on_429` — mock 429 then 200, assert retry and yield

### `tests/pipeline/transformers/test_itms.py`

- `test_transform_maps_required_fields` — full raw dict with contracts, assert canonical
- `test_transform_awarded_status` — `stav=Ukoncene` + contracts → `contract_award`
- `test_transform_active_status` — `stav=Prebieha` → `contract_notice`, `awards=[]`
- `test_transform_missing_cpv` — no CPV reference → `cpv_codes=[]`
- `test_transform_multiple_contracts` — two contracts → two awards

---

## Advantages over uvo.gov.sk scraper

| Dimension | ITMS API | UVO Scraper |
|---|---|---|
| Auth required | None | None (User-Agent spoofing) |
| Response format | JSON | HTML parsing |
| Fragility | Low | Medium-high |
| Rate limit | Relaxed (~5 req/s) | Conservative (1 req/s) |
| Coverage | EU-funded only | All procurements |
| Data quality | Structured, validated | Depends on HTML structure |
| Maintenance | Low | Medium |

These sources complement each other: ITMS gives clean structured data for EU-funded deals; UVO scraper captures the full universe. Cross-source deduplication (already in the pipeline) will link matching notices automatically.
