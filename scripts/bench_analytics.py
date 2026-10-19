"""Manual acceptance tool: cold timings and winning query plans of the dashboard aggregates.

Runs every analytics pipeline against a real MongoDB, bypassing the in-process cache,
for the default filter (last five calendar years) and an "all-time" filter (the 15-year
maximum), and prints wall-clock time, the number of rows returned and the winning plan
stages of the leading ``$match`` (``IXSCAN`` with an index name is what we want;
``COLLSCAN`` is a red flag). Read-only.

Budget (spec §7.4): cold full-range aggregate p95 <= 2 s on a prod-size corpus, hard
cap 15 s (``maxTimeMS``). Run it before the SPA defaults to "Všetko (od 2014)".

Usage:
  MONGODB_URI=mongodb://... [MONGODB_DATABASE=uvo_search] \\
    uv run python scripts/bench_analytics.py [--repeat 3] [--skip-explain]

The URI is read from the environment only (never pass credentials as arguments).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import statistics
import sys
import time
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorClient

from uvo_core.adapters.mongo.dashboards import (
    build_concentration_pipeline,
    build_coverage_pipelines,
    build_cpv_pipeline,
    build_summary_pipeline,
    build_timeseries_pipeline,
    build_top_pipeline,
    coverage_since,
)
from uvo_core.domain.analytics import DashboardFilter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bench_analytics")

MAX_TIME_MS = 15_000


def _filters(today: datetime) -> dict[str, DashboardFilter]:
    default = DashboardFilter().with_defaults(today.date())
    all_time = DashboardFilter(
        date_from=f"{today.year - 15:04d}-{today.month:02d}-{today.day:02d}",
        date_to=today.date().isoformat(),
    )
    return {"default (5y)": default, "all-time (15y)": all_time}


def _pipelines(f: DashboardFilter) -> dict[str, list[dict]]:
    return {
        "summary": build_summary_pipeline(f),
        "timeseries/month": build_timeseries_pipeline(f, "month", None, 5),
        "timeseries/month split cpv": build_timeseries_pipeline(f, "month", "cpv_division", 5),
        "top/procurer": build_top_pipeline(f, "procurer", "total_value", 10),
        "top/supplier": build_top_pipeline(f, "supplier", "total_value", 10),
        "top/cpv_division": build_top_pipeline(f, "cpv_division", "total_value", 10),
        "concentration/supplier": build_concentration_pipeline(f, "supplier"),
        "concentration/procurer": build_concentration_pipeline(f, "procurer"),
        "cpv/division": build_cpv_pipeline(f, "division"),
    }


def _plan_stages(node: object) -> list[str]:
    """Flatten a winning plan into ``STAGE(index)`` strings, leaves first."""
    out: list[str] = []
    if isinstance(node, dict):
        for child_key in ("inputStage", "inputStages", "queryPlan", "winningPlan"):
            if child_key in node:
                out.extend(_plan_stages(node[child_key]))
        stage = node.get("stage")
        if stage:
            out.append(f"{stage}({node['indexName']})" if "indexName" in node else stage)
    elif isinstance(node, list):
        for item in node:
            out.extend(_plan_stages(item))
    return out


async def _explain(db, pipeline: list[dict]) -> str:
    try:
        result = await db.command(
            {
                "explain": {"aggregate": "notices", "pipeline": pipeline, "cursor": {}},
                "verbosity": "queryPlanner",
            }
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic tool: report and carry on
        return f"explain failed: {exc}"
    planner = result.get("queryPlanner")
    if planner is None and result.get("stages"):
        planner = (result["stages"][0].get("$cursor") or {}).get("queryPlanner")
    if planner is None:
        return "no queryPlanner in explain output"
    return " -> ".join(_plan_stages(planner.get("winningPlan")))


async def _time(db, pipeline: list[dict], repeat: int) -> tuple[list[float], int]:
    timings: list[float] = []
    rows = 0
    for _ in range(repeat):
        start = time.perf_counter()
        cursor = db["notices"].aggregate(pipeline, maxTimeMS=MAX_TIME_MS, allowDiskUse=True)
        rows = len(await cursor.to_list(None))
        timings.append(time.perf_counter() - start)
    return timings, rows


async def main(repeat: int, explain: bool) -> int:
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        logger.error("MONGODB_URI is not set; nothing to benchmark")
        return 2
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5_000)
    db = client[os.environ.get("MONGODB_DATABASE", "uvo_search")]
    try:
        await client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        logger.error("MongoDB is not reachable (%s)", type(exc).__name__)
        return 2

    now = datetime.now(UTC)
    logger.info("notices: ~%d documents", await db["notices"].estimated_document_count())
    slow = 0
    for label, f in _filters(now).items():
        print(f"\n== filter: {label}  [{f.date_from} .. {f.date_to}]")
        for name, pipeline in _pipelines(f).items():
            try:
                timings, rows = await _time(db, pipeline, repeat)
            except Exception as exc:  # noqa: BLE001
                print(f"  {name:<28} FAILED: {type(exc).__name__}: {exc}")
                slow += 1
                continue
            cold = timings[0]
            median = statistics.median(timings)
            flag = "  <-- over the 2 s budget" if cold > 2.0 else ""
            slow += 1 if cold > 2.0 else 0
            print(f"  {name:<28} cold {cold:7.3f}s  median {median:7.3f}s  rows {rows}{flag}")
            if explain:
                print(f"      plan: {await _explain(db, pipeline)}")

    print("\n== coverage")
    pipelines = build_coverage_pipelines(coverage_since(now))
    for name, pipeline in pipelines.items():
        timings, rows = await _time(db, pipeline, repeat)
        print(f"  coverage/{name:<19} cold {timings[0]:7.3f}s  rows {rows}")
        if explain:
            print(f"      plan: {await _explain(db, pipeline)}")
    client.close()
    return 1 if slow else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repeat", type=int, default=3, help="runs per pipeline (first is cold)")
    parser.add_argument("--skip-explain", action="store_true", help="timings only")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(max(args.repeat, 1), not args.skip_explain)))
