# Fix Top-Suppliers Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken `top_suppliers` dashboard endpoint (which samples the first 20 alphabetical suppliers via MCP) with a direct MongoDB aggregation that returns the true global top N suppliers by contract value; also strip leading-tab corruption from ICO fields.

**Architecture:** Mirror the existing `top_procurers` pattern in `src/uvo_api/routers/dashboard.py` — skip the MCP `find_supplier` tool and aggregate directly over `notices` using `$unwind` + `$group` + `$sort`. Clean dirty ICO data in `notices` and `suppliers` collections with a one-shot repair script.

**Tech Stack:** Python 3.13, FastAPI, Motor (async MongoDB), pytest, mongosh (for manual verification)

---

## Background: What Is Wrong and Why

`GET /api/dashboard/top-suppliers` currently calls `call_tool("find_supplier", {"limit": 20})`. That MCP tool runs an Atlas `$search` with `exists` (list-all) and sorts by `name` ascending, so it returns the **first 20 suppliers alphabetically**. The dashboard then picks top 10 by `total_value` from that biased sample — guaranteeing it never shows the actual top suppliers.

Diagnosis confirmed (2026-05-05):
- The two "dominant" bars (Ing. Ondrej Seleštianský, Márk Vojtech) each have **1 contract worth €342** from CRZ. They appear first only because their names sort alphabetically before all real large suppliers.
- The true #1 supplier is MICROCOMP - Computersystém s r. o. with **€1.92B across 77 contracts** — never shown.
- 0/10 overlap between what the API shows and the true global top 10.

Additionally, two suppliers have a **leading tab character** in their ICO: `'\t3322888'` and `'\t4180850'`. This dirty data exists in both the `suppliers` and `notices` collections and needs a one-shot strip.

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `src/uvo_api/routers/dashboard.py` | **Modify** lines 158–201 | Replace `top_suppliers` implementation — drop MCP call, add direct aggregation |
| `tests/api/test_dashboard.py` | **Modify** lines 95–102 | Rewrite `test_dashboard_top_suppliers` to mock `get_db` (same pattern as `test_dashboard_top_procurers`) |
| `scripts/strip_tab_icos.py` | **Create** | One-shot repair script — strips leading/trailing whitespace from ICO fields in `suppliers` and `notices` |

---

## Task 1: Fix `top_suppliers` endpoint

The existing `top_procurers` endpoint (lines 204–231) is the exact pattern to follow. The only difference is that supplier ICO lives inside the `awards` array (`awards[].supplier.ico`, `awards[].supplier.name`), so we need a `$unwind` stage before `$group`.

**Files:**
- Modify: `src/uvo_api/routers/dashboard.py:158-201`
- Modify: `tests/api/test_dashboard.py:95-102`

- [ ] **Step 1: Write the failing test**

In `tests/api/test_dashboard.py`, replace `test_dashboard_top_suppliers` (currently lines 95–102) with:

```python
def test_dashboard_top_suppliers(client):
    mock_rows = [
        {
            "_id": "31410952",
            "name": "MICROCOMP - Computersystém s r. o.",
            "total_value": 1_921_158_287.63,
            "contract_count": 77,
        },
        {
            "_id": "35919001",
            "name": "Národná diaľničná spoločnosť, a.s.",
            "total_value": 1_379_825_579.55,
            "contract_count": 373,
        },
    ]
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=mock_rows)
    mock_collection = MagicMock()
    mock_collection.aggregate.return_value = mock_cursor
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch("uvo_api.routers.dashboard.get_db", return_value=mock_db):
        response = client.get("/api/dashboard/top-suppliers")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["ico"] == "31410952"
    assert body[0]["name"] == "MICROCOMP - Computersystém s r. o."
    assert body[0]["total_value"] == 1_921_158_287.63
    assert body[0]["contract_count"] == 77
    # Verify it is sorted by total_value descending
    assert body[0]["total_value"] >= body[1]["total_value"]
```

Also add `AsyncMock` to the imports at the top (it is already imported — confirm `from unittest.mock import AsyncMock, MagicMock, patch` is present).

- [ ] **Step 2: Run the test to confirm it fails**

```bash
wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/api/test_dashboard.py::test_dashboard_top_suppliers -v 2>&1'
```

Expected: `FAILED` — because the current implementation calls `call_tool` not `get_db`, so the `get_db` mock has no effect and the `call_tool` call tries to reach a real server.

- [ ] **Step 3: Replace the endpoint implementation**

In `src/uvo_api/routers/dashboard.py`, replace lines 158–201 (the full `top_suppliers` function including the fallback) with:

```python
@router.get("/top-suppliers", response_model=list[TopSupplier])
async def top_suppliers(
    n: int = Query(10, ge=1, le=20),
) -> list[TopSupplier]:
    db = get_db()
    pipeline = [
        {"$match": {"awards.supplier.ico": {"$nin": [None, ""]}}},
        {"$unwind": "$awards"},
        {"$match": {"awards.supplier.ico": {"$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$awards.supplier.ico",
                "total_value": {"$sum": {"$ifNull": ["$final_value", 0]}},
                "contract_count": {"$sum": 1},
                "name": {"$first": "$awards.supplier.name"},
            }
        },
        {"$sort": {"total_value": -1}},
        {"$limit": n},
    ]
    rows = await db["notices"].aggregate(pipeline).to_list(n)
    return [
        TopSupplier(
            ico=str(r["_id"]),
            name=str(r.get("name") or ""),
            total_value=float(r["total_value"]),
            contract_count=int(r["contract_count"]),
        )
        for r in rows
    ]
```

Note: the `ico` and `entity_type` query params that existed on the old endpoint are dropped — they were only used by the fallback path which is now removed. The global top is always by total value across all suppliers.

- [ ] **Step 4: Run the test to confirm it passes**

```bash
wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/api/test_dashboard.py::test_dashboard_top_suppliers -v 2>&1'
```

Expected: `PASSED`

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/api/ -v 2>&1'
```

Expected: all tests pass. If `test_dashboard_summary` fails because it patched `call_tool` for `find_supplier` — check whether `top_suppliers` is called during summary. It is not; `dashboard_summary` calls `find_supplier` separately. Investigate any failures before proceeding.

- [ ] **Step 6: Commit**

```bash
git add src/uvo_api/routers/dashboard.py tests/api/test_dashboard.py
git commit -m "fix(dashboard): replace top_suppliers MCP call with direct DB aggregation

Endpoint was fetching the first 20 suppliers alphabetically via find_supplier
(Atlas exists query + name sort) and picking top 10 by value from that
biased sample. MICROCOMP (€1.92B, 77 contracts) never appeared; two tiny
€342 CRZ contracts dominated the chart instead.

Fix mirrors top_procurers: unwind awards[], group by supplier.ico, sum
final_value, sort descending. Drops unused ico/entity_type query params
that only fed the removed fallback path."
```

---

## Task 2: Clean tab-prefixed ICO data

Diagnostic found two suppliers with a leading `\t` in their ICO: `'\t3322888'` (Branislav Burica B - l - N) and `'\t4180850'` (Ing. Peter Beneš). The tab exists in the `suppliers` collection (ico field) and likely in `notices.awards[].supplier.ico` as well. Strip whitespace from both.

**Files:**
- Create: `scripts/strip_tab_icos.py`

- [ ] **Step 1: Write the repair script**

Create `scripts/strip_tab_icos.py`:

```python
"""One-shot: strip leading/trailing whitespace from ICO fields in suppliers and notices.

Finds documents where ico or awards[].supplier.ico contains leading/trailing
whitespace (tabs, spaces, \r, \n) and updates them in-place.

Usage:
  uv run python scripts/strip_tab_icos.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017").strip()
MONGO_URI = MONGO_URI.replace("@mongo:", "@localhost:")
if "?" in MONGO_URI:
    _base, _params = MONGO_URI.split("?", 1)
    MONGO_URI = _base.rstrip("/") + "/_placeholder?" + _params
MONGO_DB = os.getenv("MONGODB_DATABASE", "uvo_search").strip()


async def fix_suppliers(db, dry_run: bool) -> int:
    """Strip whitespace from suppliers.ico where it differs from ico.strip()."""
    dirty = await db["suppliers"].find(
        {"ico": {"$regex": r"^[\s]|[\s]$"}},
        {"ico": 1, "name": 1},
    ).to_list(1000)
    if not dirty:
        print("  suppliers: no dirty ICOs found")
        return 0
    fixed = 0
    for doc in dirty:
        old = doc["ico"]
        new = old.strip()
        print(f"  suppliers: {doc.get('name', '?')!r:50s}  {old!r} -> {new!r}")
        if not dry_run:
            await db["suppliers"].update_one({"_id": doc["_id"]}, {"$set": {"ico": new}})
        fixed += 1
    return fixed


async def fix_notices(db, dry_run: bool) -> int:
    """Strip whitespace from notices.awards[].supplier.ico using arrayFilters."""
    # Find notices that have at least one award with a dirty ICO.
    dirty_cursor = db["notices"].find(
        {"awards.supplier.ico": {"$regex": r"^[\s]|[\s]$"}},
        {"_id": 1, "awards": 1, "source": 1},
    )
    dirty = await dirty_cursor.to_list(10000)
    if not dirty:
        print("  notices: no dirty supplier ICOs found")
        return 0
    fixed = 0
    for doc in dirty:
        for i, award in enumerate(doc.get("awards") or []):
            old = (award.get("supplier") or {}).get("ico") or ""
            if old != old.strip():
                new = old.strip()
                print(f"  notices[{doc['source']}]: awards[{i}].supplier.ico {old!r} -> {new!r}")
                if not dry_run:
                    await db["notices"].update_one(
                        {"_id": doc["_id"]},
                        {"$set": {f"awards.{i}.supplier.ico": new}},
                    )
                fixed += 1
    return fixed


async def main(dry_run: bool) -> None:
    uri = MONGO_URI.replace("/_placeholder?", f"/{MONGO_DB}?") if "/_placeholder?" in MONGO_URI else MONGO_URI
    client = AsyncIOMotorClient(uri, directConnection=True)
    db = client[MONGO_DB]
    try:
        print(f"{'DRY RUN — ' if dry_run else ''}Scanning for dirty ICOs...")
        s = await fix_suppliers(db, dry_run)
        n = await fix_notices(db, dry_run)
        print(f"\nTotal: {s} supplier docs, {n} notice awards {'would be ' if dry_run else ''}fixed.")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
```

- [ ] **Step 2: Dry-run to preview changes**

```bash
wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && set -a && source .env && set +a && uv run python scripts/strip_tab_icos.py --dry-run 2>&1'
```

Expected output lists the two known dirty ICOs (`\t3322888`, `\t4180850`) in both suppliers and notices. If more appear, review before proceeding.

- [ ] **Step 3: Apply the fix**

```bash
wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && set -a && source .env && set +a && uv run python scripts/strip_tab_icos.py 2>&1'
```

Expected: same list of ICOs, no `DRY RUN` prefix, "X supplier docs, Y notice awards fixed."

- [ ] **Step 4: Verify via diagnostic script**

```bash
wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && set -a && source .env && set +a && uv run python scripts/diagnose_top_suppliers.py 2>&1'
```

Expected in Section 4 (Sampling Bias):
- `False positives in API (not in global top)` should no longer contain tab-prefixed ICOs.

Expected in Section 1 (Dashboard API): The two top entries should now be MICROCOMP and Národná diaľničná spoločnosť (or similar large suppliers), not tiny CRZ contracts.

- [ ] **Step 5: Commit**

```bash
git add scripts/strip_tab_icos.py
git commit -m "fix(data): strip leading-tab whitespace from supplier ICO fields

Two supplier records had '\t'-prefixed ICOs (\t3322888, \t4180850)
causing them to appear in the top-suppliers chart with 0 value (ICO
mismatch on notices lookup). Repair script strips whitespace from
suppliers.ico and notices.awards[].supplier.ico in-place."
```

---

## Verification

After both tasks, run the full API test suite one more time:

```bash
wsl -e bash -lc 'cd /mnt/c/Users/User/Documents/src/uvo-search && uv run pytest tests/api/ -v 2>&1'
```

And confirm the live dashboard shows real top suppliers by opening the overview page at `http://localhost:8080` (or `http://localhost:5174` in dev mode) — MICROCOMP or Národná diaľničná spoločnosť should now lead the chart with values in the billions.
