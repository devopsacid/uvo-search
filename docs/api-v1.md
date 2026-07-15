# UVO Public API v1

Monetizable, versioned public API for Slovak government procurement data. Served
by `uvo_api` as a standalone sub-app mounted at `/v1`. Interactive docs render at
`/v1/docs` (OpenAPI schema at `/v1/openapi.json`) and contain only the public
endpoints — the internal `/api/*` routes are not exposed.

## Authentication

Every `/v1` request requires an API key in the `X-API-Key` header. Keys are
stored in the Mongo `api_keys` collection as a sha256 hash of the raw key.

Issue and revoke keys with the CLI:

```bash
# Issue a key (raw key is printed once)
uv run python -m scripts.issue_api_key --email you@example.com --plan pro

# Revoke by the printed prefix
uv run python -m scripts.issue_api_key --revoke uvo_a1b2c3d4
```

Plans: `free`, `pro`, `business`.

Auth errors use the standard error model:

```json
{ "error": { "code": "missing_api_key", "message": "Provide an API key in the X-API-Key header." } }
```

`code` is one of `missing_api_key`, `invalid_api_key` (both HTTP 401).

## Rate limits

Fixed-window (per calendar minute) per key, enforced via Redis:

| Plan     | Requests / min |
| -------- | -------------- |
| free     | 30             |
| pro      | 300            |
| business | 1000           |

On exceeding the limit the API returns HTTP 429 with a `Retry-After` header:

```json
{ "error": { "code": "rate_limit_exceeded", "message": "Rate limit of 30 requests/min exceeded for plan 'free'.", "retry_after": 42 } }
```

## Response envelope & pagination

List endpoints return a consistent envelope:

```json
{ "data": [ ... ], "pagination": { "next_cursor": "MjA=" } }
```

`next_cursor` is an opaque, base64-encoded offset. Pass it back as the `cursor`
query param to fetch the next page. `null` means no more results. A malformed
cursor returns HTTP 400 (`code: invalid_cursor`). Single-object endpoints wrap
the object in `data` with an empty `pagination`.

## Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/v1/companies` | Search companies (suppliers + procurers) by name (`q`, `cursor`, `limit`). |
| GET | `/v1/companies/{ico}` | Core company record (name, roles). |
| GET | `/v1/companies/{ico}/profile` | Procurement profile: contract count & total value, spend by year, top counterparties, CPV breakdown + concentration (HHI). |
| GET | `/v1/companies/{ico}/risk` | Red-flag risk profile: 0-100 score, band, and per-flag detail with evidence. |
| GET | `/v1/contracts` | Search contracts (`q`, `cpv`, `date_from`, `date_to`, `min_value`, `cursor`, `limit`). |
| GET | `/v1/contracts/{id}` | Contract/notice detail. |

`limit` ranges 1–100 (default 20). `404` responses use `code: company_not_found`
or `code: contract_not_found`.

### Risk profile

`GET /v1/companies/{ico}/risk` blends four independent red flags into an overall
`risk_score` (0-100) and `risk_band` (`low` / `moderate` / `high`). Each flag
reports whether it `triggered`, its own `severity` and `score`, a human-readable
`summary`, and the `evidence` it was computed from:

| Flag | Signal |
| ---- | ------ |
| `supplier_concentration` | Herfindahl-Hirschman index over the authority's per-supplier awarded value (single-source dependency). |
| `repeat_pair_share` | Share of the company's total value concentrated on one counterparty. |
| `market_deviation` | Average contract value vs. the CPV-market average (over/under-pricing outlier). |
| `award_clustering` | Bursts of awards to the same counterparty in a short window (contract-splitting signal). |

```json
{
  "data": {
    "ico": "12345678",
    "name": "Example s.r.o.",
    "roles": ["procurer"],
    "risk_score": 62.5,
    "risk_band": "high",
    "flags": [
      {
        "code": "supplier_concentration",
        "triggered": true,
        "severity": "high",
        "score": 100.0,
        "summary": "Supplier-spend concentration HHI 1.00 (high).",
        "evidence": { "hhi": 1.0, "supplier_count": 1, "top_supplier": { "ico": "87654321", "name": "Sole Vendor", "value_share": 1.0 } }
      }
    ]
  },
  "pagination": { "next_cursor": null }
}
```

Flag semantics follow zákon 343/2015 red-flag conventions; thresholds are
conservative module constants documented in `uvo_core/domain/scoring.py`.

## Usage metering

Each request from an authenticated key appends `{key_id, endpoint, status, ts}`
to the Redis stream `api:usage` (capped at ~100k entries). Metering is
best-effort and never fails a request. No rollup worker ships in this prototype.

## Examples

```bash
BASE=http://localhost:8001
KEY=uvo_your_raw_key

# Company search
curl -s -H "X-API-Key: $KEY" "$BASE/v1/companies?q=stavby&limit=5"

# Company profile
curl -s -H "X-API-Key: $KEY" "$BASE/v1/companies/12345678/profile"

# Company risk profile
curl -s -H "X-API-Key: $KEY" "$BASE/v1/companies/12345678/risk"

# Contract search
curl -s -H "X-API-Key: $KEY" \
  "$BASE/v1/contracts?q=cesty&cpv=45000000&date_from=2023-01-01&min_value=100000"

# Next page
curl -s -H "X-API-Key: $KEY" "$BASE/v1/companies?q=stavby&cursor=NQ=="
```

## Configuration

`uvo_api` reads (env prefix `API_`):

- `API_REDIS_URL` (default `redis://redis:6379/0`)
- `API_REDIS_PASSWORD` (optional)
- `API_MONGODB_URI`, `API_MONGODB_DATABASE` (for the `api_keys` collection)
