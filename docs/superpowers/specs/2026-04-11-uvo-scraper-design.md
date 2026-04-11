# Design: uvo.gov.sk Scraper Integration

**Date:** 2026-04-11
**Status:** Approved
**Source:** uvo.gov.sk (Úrad pre verejné obstarávanie — Office for Public Procurement)

---

## Context

uvo.gov.sk is the official Slovak public procurement portal. It has no public API — it runs on TYPO3 CMS and returns server-rendered HTML. The contract search at `/vyhladavanie/vyhladavanie-zakaziek` supports pagination via `limit` and `page` query parameters and contains enough structured data in both listing rows and detail pages to populate the canonical notice model.

This integration replaces the removed UVOstat extractor as the primary source of Slovak procurement notices.

---

## Scope

- Full backfill from 2014 to present (historical mode)
- Incremental updates from last checkpoint (recent mode)
- Both listing data and detail page data (procurer, supplier, award, CPV, value)
- Fits the existing extractor → transformer → orchestrator pattern

Out of scope: document downloads, profile pages, NUTS codes (not in listing/detail summary), appeal/complaint records.

---

## Architecture

```
uvo.gov.sk HTML
      │
      ▼
extractors/uvo.py          async generator — paginates listing, fetches details
      │  yields raw dicts
      ▼
transformers/uvo.py        transform_notice(raw) → CanonicalNotice
      │
      ▼
orchestrator.py            Step N (after TED) — wired into run()
      │
      ▼
MongoDB + Neo4j loaders    same as all other sources
```

New files:
- `src/uvo_pipeline/extractors/uvo.py`
- `src/uvo_pipeline/transformers/uvo.py`

Modified files:
- `src/uvo_pipeline/config.py` — 4 new settings
- `src/uvo_pipeline/orchestrator.py` — new extraction step + checkpoint
- `src/uvo_pipeline/models.py` — add `"uvo"` to `CanonicalNotice.source` Literal

Test files:
- `tests/pipeline/extractors/test_uvo.py`
- `tests/pipeline/transformers/test_uvo.py`

---

## Extractor: `extractors/uvo.py`

### Public interface

```python
async def fetch_notices(
    client: httpx.AsyncClient,
    rate_limiter: AsyncLimiter,
    *,
    from_date: date,
    to_date: date,
    fetch_details: bool = True,
    max_pages: int | None = None,
) -> AsyncIterator[dict]
```

### Listing phase

URL: `GET https://www.uvo.gov.sk/vyhladavanie/vyhladavanie-zakaziek?limit=100&page={n}`

Optional date filters appended when available. Pages are fetched in descending date order (newest first). Pagination stops when the oldest notice on a page has `published_date < from_date`, or when an empty page is returned.

Each listing row is parsed with BeautifulSoup to extract:

| Field | Source |
|---|---|
| `id` | Row link href (`/detail/{id}`) |
| `title` | Title cell text |
| `procurer_name` | Procurer cell text |
| `procurer_ico` | Procurer cell sub-text or separate column |
| `cpv` | CPV cell (first code if multiple) |
| `published_date` | Date cell (DD.MM.YYYY → ISO) |
| `status` | Status badge text |
| `estimated_value` | Value cell (numeric, strip currency) |
| `detail_url` | Full href including `cHash` param |
| `notice_type_raw` | Procedure type label |

### Detail phase

URL: `GET {detail_url}` (cHash already embedded from listing href)

Each detail page is parsed to extract:

| Field | Source |
|---|---|
| `supplier_name` | Winner/dodávateľ section |
| `supplier_ico` | Winner ICO |
| `final_value` | Finálna suma |
| `award_date` | Date of award |
| `procedure_type` | Druh postupu |
| `notice_type_raw` | Druh zákazky (refined from listing) |
| `currency` | Mena |

If `fetch_details=False`, detail fields are omitted (listing-only mode, faster backfill).

Detail fetch is skipped for notices already present in MongoDB (`source="uvo"`, `source_id` match) — avoids redundant HTTP requests on incremental runs.

### Rate limiting

Uses the existing `aiolimiter.AsyncLimiter` pattern shared across extractors. Default: 1 req/s. A `uvo_request_delay` float (default 0.5s) is added between each request as a polite floor, independent of rate limiting.

User-Agent header: `Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0`

### Error handling

- HTTP 429 / 503: exponential backoff, max 3 retries, then log warning and skip
- Parse errors on a single notice: log warning, skip that notice, continue
- Empty page: stop pagination

---

## Transformer: `transformers/uvo.py`

```python
def transform_notice(raw: dict) -> CanonicalNotice
```

### Field mapping

| Raw field | Canonical field | Notes |
|---|---|---|
| `id` | `source_id` | String |
| `"uvo"` | `source` | Literal |
| `title` | `title` | Stripped |
| `published_date` | `published_date` | ISO date |
| `cpv` | `cpv_code` | First code only |
| `estimated_value` | `estimated_value` | Float or None |
| `status` | `status` | Mapped (see below) |
| `notice_type_raw` | `notice_type` | Mapped (see below) |
| `procurer_name` + `procurer_ico` | `procurer: CanonicalProcurer` | |
| `supplier_name` + `supplier_ico` | `awards[0].supplier` | Only if detail fetched |
| `final_value` | `awards[0].value` | Float or None |
| `currency` | `awards[0].currency` | Default `"EUR"` |

### Status mapping

| UVO status | Canonical status |
|---|---|
| Ukončené / Zmluvne ukončené | `awarded` |
| Zrušené | `cancelled` |
| Prebiehajúce / Vyhlásené | `announced` |
| anything else | `unknown` |

### Notice type mapping

| UVO type | Canonical type |
|---|---|
| Zákazka / Verejná zákazka | `contract_notice` |
| Zmluva / Výsledok | `contract_award` |
| Predbežné oznámenie | `prior_information` |
| Oprava | `other` |
| anything else | `other` |

### Missing data

All fields except `source`, `source_id`, `title`, `published_date` default to `None` / `[]`. No exception thrown for missing fields.

---

## Orchestrator wiring

New extraction step added after TED in `orchestrator.run()`:

```python
# Step N — UVO.gov.sk
if settings.uvo_fetch_details:
    uvo_from = checkpoint.get("uvo") or (
        date(2014, 1, 1) if mode == "historical" else today - timedelta(days=365)
    )
    async for raw in fetch_notices(client, rate_limiter, from_date=uvo_from, to_date=today):
        notice = transform_notice(raw)
        batch.append(notice)
        # flush batch every settings.batch_size notices
    checkpoint["uvo"] = today.isoformat()
```

Historical mode loops year-by-year (`from_date=Jan 1 YYYY`, `to_date=Dec 31 YYYY`) to avoid accumulating a massive in-memory batch.

---

## Config additions (`config.py`)

```python
uvo_base_url: str = "https://www.uvo.gov.sk"
uvo_rate_limit: float = 1.0        # max requests per second
uvo_request_delay: float = 0.5     # extra polite delay between requests (seconds)
uvo_fetch_details: bool = True     # False = listing-only, no detail page fetches
```

All overridable via environment variables (`UVO_BASE_URL`, `UVO_RATE_LIMIT`, etc.).

---

## Models change

Add `"uvo"` to the `source` Literal in `CanonicalNotice`:

```python
source: Literal["crz", "ted", "vestnik", "uvo"]
```

---

## Testing

### `tests/pipeline/extractors/test_uvo.py`

- `test_fetch_listing_yields_notices` — mock one listing page HTML, assert raw dict fields
- `test_fetch_stops_at_from_date` — listing with mixed old/new dates, assert stops at boundary
- `test_fetch_detail_extracts_supplier` — mock detail HTML, assert supplier/award fields
- `test_fetch_skips_detail_when_already_in_db` — mock MongoDB hit, assert no detail HTTP call
- `test_fetch_retries_on_503` — mock 503 then 200, assert retry and eventual yield
- `test_fetch_listing_only_mode` — fetch_details=False, assert no detail calls made
- `test_pagination_stops_on_empty_page` — empty page returns [], assert generator stops

### `tests/pipeline/transformers/test_uvo.py`

- `test_transform_maps_required_fields` — full raw dict, assert all canonical fields
- `test_transform_handles_missing_supplier` — no supplier in raw, assert awards=[]
- `test_transform_status_mapping` — parametrized, all status strings
- `test_transform_notice_type_mapping` — parametrized, all notice type strings
- `test_transform_missing_value_is_none` — no estimated_value in raw, assert None

---

## Open questions resolved

- **cHash**: Extracted from listing page href — no need to compute, server provides it
- **Date filtering**: UVO listing supports `?date_from=` and `?date_to=` params (to be verified during implementation; fall back to client-side date filtering if not available)
- **Pagination direction**: Newest-first (default sort), so historical mode stops early once dates go below threshold
- **Block risk**: Polite rate limit (1 req/s) + Firefox User-Agent should be sufficient; if blocked, increase `uvo_request_delay`
