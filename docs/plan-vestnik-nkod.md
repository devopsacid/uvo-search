# Plan: Vestník NKOD extractor (replace dead CKAN source)

## Context

The CKAN extractor `catalog/ckan.py` is disabled — `data.gov.sk` has been replaced by the React SPA `data.slovensko.sk` which no longer exposes CKAN. The replacement SPA is backed by a **public SPARQL endpoint** at `POST https://data.slovensko.sk/api/sparql` (DCAT-AP catalog).

UVO's publisher URI: `https://data.gov.sk/id/legal-subject/31797903`. Each weekly "Vestník N/YYYY" is a `dcat:Dataset` with one `dcat:Distribution` (JSON, ~10 MB) linked via `dcat:accessURL` = `https://data.slovensko.sk/download?id=<uuid>`.

Historical coverage: weekly bulletins back to 2016+ (~520 issues, ~100k notices total).

## Data shape (verified)

**Bulletin envelope (JSON)**:

```json
{
  "bulletinPublishDate": "2026-04-17T01:02:38.215622",
  "year": 2026,
  "number": 76,
  "bulletinItemList": [
    { "itemData": "<JSON string — one notice form>" }
  ]
}
```

**Notice form** (inside `itemData`, parsed as JSON):

```json
{
  "id": 1397309,
  "name": "Oznámenie o výsledku verejného obstarávania (D24)",
  "components": [
    { "key": "metadataWrapper", "components": [ ...eForms BT fields... ] },
    { "key": "tabs",            "components": [ ...sections with lots, parties, values... ] }
  ]
}
```

Fields use **EU eForms Business Term codes** (eForms SDK 1.13 confirmed via `OPT-002-notice`). Key codes seen:

| Code | Meaning | Example value |
|---|---|---|
| `DL-Metadata-Partner` | Procuring org (name + internal id) | `Hlavné mesto SR Bratislava (ID: 39686)` |
| `DL-Metadata-Order`   | Procurement title + order id     | `IT HW a podpora (ID: 422123)` |
| `BT-02-notice` | Notice form subtype | `can-standard` (contract-award-notice) |
| `BT-03-notice` | Notice purpose | `result`, `planning`, `change` |
| `BT-04-notice` | Notice UUID (stable across republications) | `9699fa41-…` |
| `OPT-002-notice` | eForms SDK version | `eforms-sdk-1.13` |

eForms codes give us a stable, language-independent extraction key — safer than scraping Slovak labels.

## Target: eight-step implementation

### 1. `src/uvo_pipeline/catalog/nkod.py` — SPARQL discovery

- Single function `async def discover_vestnik_datasets(client, *, since: date | None) -> AsyncIterator[VestnikDataset]`.
- `VestnikDataset = dataclass(uri, title, publish_date, modified, download_url)`.
- SPARQL query:
  ```sparql
  PREFIX dcat: <http://www.w3.org/ns/dcat#>
  PREFIX dct:  <http://purl.org/dc/terms/>
  SELECT ?dataset ?title ?issued ?modified ?url WHERE {
    ?dataset a dcat:Dataset ;
             dct:publisher <https://data.gov.sk/id/legal-subject/31797903> ;
             dct:title ?title ;
             dcat:distribution ?dist .
    ?dist dcat:accessURL ?url .
    OPTIONAL { ?dataset dct:issued   ?issued }
    OPTIONAL { ?dataset dct:modified ?modified }
    FILTER (lang(?title) = "sk")
    FILTER (?modified >= "<since>"^^xsd:dateTime)   # conditional
  } ORDER BY ?modified
  ```
- Paginate via `LIMIT 200 OFFSET n` until empty page.
- HTTP `POST` with body `query=<encoded>` and `Accept: application/sparql-results+json`.

### 2. `src/uvo_pipeline/extractors/vestnik_nkod.py` — download + parse

- `async def fetch_bulletin(client, rate_limiter, dataset: VestnikDataset) -> AsyncIterator[dict]`:
  - `GET` the download_url (follows redirects, ~10 MB), stream to memory (they're small enough) or tempfile.
  - Parse outer JSON → iterate `bulletinItemList`.
  - For each item: `raw = json.loads(item["itemData"])` then add context: `raw["_bulletin_year"]`, `raw["_bulletin_number"]`, `raw["_bulletin_publish_date"]`, `raw["_dataset_uri"]`.
  - Yield each enriched notice dict.
- Cache bulletin downloads on disk (`$cache_dir/vestnik/<uuid>.json`) keyed by `dataset.uri` — idempotent re-runs skip re-download.

### 3. `src/uvo_pipeline/transformers/vestnik_nkod.py`

- Helper `_flatten_eforms(components) -> dict[str, str]` that recursively walks `components[]` and builds `{bt_code: value}`.
- Helper `_lookup(flat, *codes)` returns first non-empty value among alternative BT codes (different form subtypes use different BT codes for the same logical field).
- `transform_notice(raw: dict) -> CanonicalNotice`:
  - `source = "vestnik"`, `source_id = str(raw["id"])`
  - `ted_notice_id = flat.get("BT-04-notice")` (UUID — reusable for cross-source dedup vs TED)
  - `notice_type` from `BT-03-notice`: `result→contract_award`, `planning→contract_notice`, `change→modification`, else `other`
  - `status`: derived from `notice_type`
  - `title`: parse `DL-Metadata-Order` (strip trailing ` (ID: …)`), fall back to `raw["name"]`
  - `procurer`: parse `DL-Metadata-Partner` → name + extract internal id as `source_ref`; no ICO in the eForms payload, so leave `ico=None` for now (Phase 2 idea: join by `OPP-*` org URIs).
  - `publication_date`: `raw["_bulletin_publish_date"]` (date part)
  - `final_value` / `estimated_value` + `currency`: BT codes for monetary amounts (`BT-27-Lot` estimated, `BT-720-Tender` final-value, `BT-5-...` etc. — specifics come from eForms SDK). TODO doc.
  - `cpv_code`: `BT-262-Lot` (main CPV). Lots are repeated sections; take the first for Phase 1, multi-lot support in Phase 2.

### 4. Orchestrator wiring

In `orchestrator.py`, **replace** the CKAN Vestník block (lines ~227–256) with:
```python
from uvo_pipeline.catalog.nkod import discover_vestnik_datasets
from uvo_pipeline.extractors.vestnik_nkod import fetch_bulletin
from uvo_pipeline.transformers.vestnik_nkod import transform_notice as transform_vestnik

logger.info("Extracting from Vestník NKOD (since=%s)...", vestnik_since)
async with httpx.AsyncClient(timeout=settings.request_timeout) as sparql_client:
    async with httpx.AsyncClient(timeout=settings.request_timeout, follow_redirects=True) as dl_client:
        async for ds in discover_vestnik_datasets(sparql_client, since=vestnik_since):
            async for raw in fetch_bulletin(dl_client, vestnik_rate_limiter, ds):
                try:
                    notice = transform_vestnik(raw)
                    notice.pipeline_run_id = run_id
                    all_notices.append(notice)
                    vestnik_count += 1
                except Exception as exc:
                    logger.warning("Vestník transform error (item id=%s): %s", raw.get("id"), str(exc).splitlines()[0])
```

Keep the old CKAN module around for one release then delete; leave a `# DELETED on <date>:` marker in `__init__.py`.

### 5. Checkpoint

- Add `vestnik_last_modified: str` to the pipeline checkpoint.
- Compute `vestnik_since = checkpoint.get("vestnik_last_modified") or (today - recent_days)`.
- After a successful load, save `max(ds.modified for ds in processed)`.
- Historical mode: `since=None` → full re-ingest (~5 GB download, one-shot).

### 6. Configuration

Add to `config.py`:
- `nkod_sparql_url: str = "https://data.slovensko.sk/api/sparql"`
- `vestnik_rate_limit: float = 2.0` (conservative — large downloads)
- `uvo_publisher_uri: str = "https://data.gov.sk/id/legal-subject/31797903"`

### 7. Tests (mirror ITMS test style)

- `tests/pipeline/catalog/test_nkod.py`: respx-mocked SPARQL endpoint returning a small JSON results payload; assert iterator yields `VestnikDataset` tuples with correct fields.
- `tests/pipeline/extractors/test_vestnik_nkod.py`: fixture with a minimal bulletin JSON (2 items), respx-mocked download URL, assert items are yielded with context fields.
- `tests/pipeline/transformers/test_vestnik_nkod.py`: table-driven over `BT-03-notice` values (`result`, `planning`, `change`) → expected `notice_type` + `status`; org-name parsing; BT-04 UUID flows to `ted_notice_id`; multi-lot dataset uses first CPV.

### 8. Rollout

- Land code + tests (branch).
- **Deploy without clearing data** — new source adds to existing 53k notices.
- First run: `since=today - 90d` → ~13 bulletins, ~1.2k notices, ~130 MB download. Verify cleanly.
- Historical backfill: one-shot script (like the ITMS enrichment) that runs with `since=None`. ~520 bulletins, ~5 GB, one overnight run. Idempotent via content-hash dedup.

## Open questions / decisions

1. **Where to store eForms BT→canonical-field mapping?** Inline `dict` in transformer is fine for Phase 1, but the full mapping is ~30 codes. Move to `transformers/vestnik_eforms_mapping.py` once stable.
2. **ICO resolution.** The bulletin only carries internal IDs like `(ID: 39686)`. Cross-referencing to ICO would require either (a) a `/v2/subjekty`-style UVO registry or (b) pulling from the eForms party sections which sometimes embed `<cbc:CompanyID>`. Tackle in Phase 2.
3. **Multi-lot**. Each notice can have N lots, each with its own CPV/value/supplier. Phase 1: keep the one-notice-per-item model and take lot[0]. Phase 2: emit one `CanonicalNotice` per lot OR add `lots: list[CanonicalLot]` to the model.
4. **Dedup with TED**. TED's `publication-number` and Vestník's `BT-04-notice` are both EU-wide notice UUIDs. `ted_notice_id` on both sides + hash comparison should catch cross-source duplicates automatically via the existing dedup logic.

## Estimated effort

- Steps 1–3 (SPARQL + extractor + transformer): ~4h
- Step 4 (orchestrator wiring): ~30min
- Step 5 (checkpoint): ~30min
- Step 6 (config): ~10min
- Step 7 (tests): ~2h
- Step 8 (rollout + first historical backfill): overnight

**Total hands-on time: ~7h code, + overnight for historical backfill.**
