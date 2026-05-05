"""Diagnose and validate the top-suppliers dashboard data.

Checks:
1. What the dashboard API currently returns (biased sample or true global).
2. The true global top-N suppliers by total contract value (direct aggregation).
3. Integrity of the two dominant entries: ICO validity, notice-match correctness.
4. Sampling-bias summary comparing API vs global result.

Usage:
  uv run python scripts/diagnose_top_suppliers.py [--top N] [--api-url URL] [--container NAME]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8001")
MONGO_CONTAINER = "uvo-search-mongo-1"
MONGO_DB = os.getenv("MONGODB_DATABASE", "uvo_search").strip()
_raw_uri = os.getenv("MONGODB_URI", "mongodb://uvo:changeme@mongo:27017/?authSource=admin").strip()
# Inside the container, service name resolves to localhost.
MONGOSH_URI = _raw_uri.replace("@mongo:", "@localhost:")

SEP = "-" * 72


def _fmt(v: float) -> str:
    if v >= 1_000_000:
        return f"€{v/1_000_000:,.2f}M"
    if v >= 1_000:
        return f"€{v/1_000:,.1f}k"
    return f"€{v:,.0f}"


def _mongosh(js: str, container: str, db: str) -> list[dict]:
    """Run JS in mongosh inside the Docker container, return parsed JSON array."""
    # Insert db before the query-string: mongodb://user:pw@host:port/DB?params
    if "?" in MONGOSH_URI:
        base, params = MONGOSH_URI.split("?", 1)
        uri = base.rstrip("/") + "/" + db + "?" + params
    else:
        uri = MONGOSH_URI.rstrip("/") + "/" + db
    cmd = [
        "docker", "exec", container,
        "mongosh", "--quiet", uri,
        "--eval", js,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"  [mongosh error] {result.stderr.strip()}", file=sys.stderr)
        return []
    out = result.stdout.strip()
    if not out:
        return []
    # mongosh --json relaxed may emit EJSON; parse outer array
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        # try line-by-line in case of multiple results
        rows = []
        for line in out.splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return rows


async def check_api(n: int, api_url: str) -> list[dict]:
    print(f"\n{SEP}")
    print("1. DASHBOARD API  GET /api/dashboard/top-suppliers")
    print(SEP)
    async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
        r = await client.get("/api/dashboard/top-suppliers", params={"n": n})
        r.raise_for_status()
        data = r.json()
    for i, s in enumerate(data, 1):
        print(f"  {i:2d}. {s['name'][:45]:<45} ico={s['ico']:<12} "
              f"value={_fmt(s['total_value']):>12}  count={s['contract_count']}")
    return data


def true_global_top(n: int, container: str, db: str) -> list[dict]:
    print(f"\n{SEP}")
    print("2. TRUE GLOBAL TOP (direct aggregation via mongosh)")
    print(SEP)
    js = f"""
JSON.stringify(db.notices.aggregate([
  {{$match: {{"awards.supplier.ico": {{$nin: [null, ""]}}}}}},
  {{$unwind: "$awards"}},
  {{$match: {{"awards.supplier.ico": {{$nin: [null, ""]}}}}}},
  {{$group: {{
    _id: "$awards.supplier.ico",
    name: {{$first: "$awards.supplier.name"}},
    total_value: {{$sum: {{$ifNull: ["$final_value", 0]}}}},
    contract_count: {{$sum: 1}}
  }}}},
  {{$sort: {{total_value: -1}}}},
  {{$limit: {n}}}
], {{allowDiskUse: true}}).toArray())
"""
    rows = _mongosh(js, container, db)
    if rows and isinstance(rows[0], list):
        rows = rows[0]
    for i, r in enumerate(rows, 1):
        print(f"  {i:2d}. {(r.get('name') or '')[:45]:<45} ico={r.get('_id', ''):<12} "
              f"value={_fmt(r.get('total_value', 0)):>12}  count={r.get('contract_count', 0)}")
    return rows


def validate_dominant(api_entries: list[dict], container: str, db: str) -> None:
    top2 = api_entries[:2]
    if not top2:
        return
    print(f"\n{SEP}")
    print("3. ICO & NOTICE INTEGRITY CHECK (top 2 API entries)")
    print(SEP)

    for entry in top2:
        ico = entry.get("ico") or ""
        name = entry.get("name") or ""
        print(f"\n  Supplier: {name}  (ico={ico!r})")

        if not ico:
            js = f"""
JSON.stringify([{{
  suppliers_match: db.suppliers.countDocuments({{name: {json.dumps(name)}}}),
  notices_empty_ico: db.notices.countDocuments({{"awards.supplier.ico": {{$in: [null, ""]}}}})
}}])
"""
            rows = _mongosh(js, container, db)
            r = (rows[0] if rows else {}) if not isinstance(rows[0] if rows else None, list) else (rows[0][0] if rows[0] else {})
            print(f"    WARNING: empty ICO")
            print(f"    suppliers with this name: {r.get('suppliers_match', '?')}")
            print(f"    notices with null/empty supplier ICO: {r.get('notices_empty_ico', '?')}")
            continue

        js = f"""
var ico = {json.dumps(ico)};
var supplierDoc = db.suppliers.findOne({{ico: ico}});
var noticeCount = db.notices.countDocuments({{"awards.supplier.ico": ico}});
var sample = db.notices.find(
  {{"awards.supplier.ico": ico}},
  {{source: 1, title: 1, final_value: 1, "awards.supplier": 1}}
).sort({{final_value: -1}}).limit(5).toArray();
var nameAgg = db.notices.aggregate([
  {{$match: {{"awards.supplier.ico": ico}}}},
  {{$unwind: "$awards"}},
  {{$match: {{"awards.supplier.ico": ico}}}},
  {{$group: {{_id: "$awards.supplier.name", count: {{$sum: 1}}}}}},
  {{$sort: {{count: -1}}}},
  {{$limit: 5}}
]).toArray();
JSON.stringify({{
  supplier_found: supplierDoc != null,
  supplier_sources: supplierDoc ? supplierDoc.sources : null,
  notice_count: noticeCount,
  sample: sample,
  name_variants: nameAgg
}})
"""
        rows = _mongosh(js, container, db)
        if isinstance(rows, dict):
            r = rows
        elif rows and isinstance(rows[0], dict):
            r = rows[0]
        elif rows and isinstance(rows[0], list):
            r = rows[0][0] if rows[0] else {}
        else:
            r = {}

        if r.get("supplier_found"):
            print(f"    suppliers coll: found  sources={r.get('supplier_sources')}")
        else:
            print("    suppliers coll: NOT FOUND (entry derived from notices only)")

        print(f"    notices matching ico {ico!r}: {r.get('notice_count', '?')}")

        for j, notice in enumerate(r.get("sample") or [], 1):
            awards = notice.get("awards") or [{}]
            sup = awards[0].get("supplier", {}) if awards else {}
            print(f"      [{j}] source={str(notice.get('source','')):<8} "
                  f"value={_fmt(notice.get('final_value') or 0):>12}  "
                  f"supplier_ico={sup.get('ico')!r}  "
                  f"title={str(notice.get('title') or '')[:40]}")

        variants = r.get("name_variants") or []
        if len(variants) > 1:
            print(f"    ICO COLLISION — {len(variants)} different names share ICO {ico!r}:")
            for v in variants:
                print(f"      {v.get('count', 0):>5}x  {v.get('_id')}")
        else:
            print(f"    ICO clean — single name under this ICO")


def sampling_bias_check(api_entries: list[dict], global_top: list[dict]) -> None:
    print(f"\n{SEP}")
    print("4. SAMPLING BIAS SUMMARY")
    print(SEP)

    api_icos = {e.get("ico") for e in api_entries}
    global_icos = {r.get("_id") for r in global_top}
    overlap = api_icos & global_icos
    missing = global_icos - api_icos
    false_positives = api_icos - global_icos

    print(f"  API returned {len(api_icos)} suppliers; global top has {len(global_icos)}")
    print(f"  Overlap (correct):              {len(overlap)}")
    print(f"  Global top MISSED by API:       {len(missing)}")
    print(f"  API entries NOT in global top:  {len(false_positives)}")

    if missing:
        missed = [r for r in global_top if r.get("_id") in missing]
        print("\n  True top suppliers missed by the API:")
        for r in missed:
            print(f"    ico={r.get('_id', ''):<12} value={_fmt(r.get('total_value', 0)):>12}  {r.get('name', '')}")
    if false_positives - {None, ""}:
        print(f"\n  False positives in API (not in global top): {false_positives - {None, ''}}")


async def main(n: int, api_url: str, container: str) -> None:
    api_entries = await check_api(n, api_url)
    global_top = true_global_top(n, container, MONGO_DB)
    validate_dominant(api_entries, container, MONGO_DB)
    sampling_bias_check(api_entries, global_top)
    print(f"\n{SEP}\nDone.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=10, metavar="N")
    parser.add_argument("--api-url", default=API_URL)
    parser.add_argument("--container", default=MONGO_CONTAINER)
    args = parser.parse_args()
    asyncio.run(main(args.top, args.api_url, args.container))
