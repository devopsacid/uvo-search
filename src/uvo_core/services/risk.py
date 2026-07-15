"""Company red-flag risk profile — the first pure-domain consumer (plan Phase 4).

Fetches its inputs ONLY through the ``CompanyAnalytics`` and ``GraphStore`` ports,
feeds them to the pure functions in :mod:`uvo_core.domain.scoring`, and assembles
the profile. No motor/neo4j import here — that is the port-boundary validation gate.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict

from uvo_core.domain.scoring import (
    RISK_DISCLAIMER,
    RiskFlag,
    award_clustering,
    is_framework_or_dns,
    market_deviation,
    repeat_pair_share,
    risk_summary,
    supplier_concentration,
)
from uvo_core.ports import CompanyAnalytics, GraphStore

# Enough rows for stable HHI / worst-pair math without unbounded fan-out.
_PARTNER_FETCH = 100
# Cover more than the market top-20 so mid-value CPVs the company uses still match.
_MARKET_CPV_FETCH = 200


def _worst_award_cluster(timeline: list[dict]) -> RiskFlag:
    """Group the award timeline by counterparty, keep the densest-burst flag.

    Framework-agreement / DNS call-offs legitimately cluster in time (they are the
    known false-positive source), so awards whose ``procedure_type`` marks one are
    excluded before grouping. Each award carries its ``cpv_code`` and ``value`` so
    the scoring can apply the shared-CPV-division and low-value-ceiling guards.
    """
    by_counterparty: dict[str, list[dict]] = defaultdict(list)
    for row in timeline:
        ico = row.get("counterparty_ico")
        date = row.get("date")
        if not ico or not date:
            continue
        if is_framework_or_dns(row.get("procedure_type")):
            continue
        by_counterparty[ico].append(
            {"date": date, "cpv_code": row.get("cpv_code"), "value": row.get("value")}
        )

    worst = award_clustering([])
    worst_ico: str | None = None
    for ico, awards in by_counterparty.items():
        flag = award_clustering(awards)
        if flag.score > worst.score:
            worst, worst_ico = flag, ico
    if worst_ico is not None:
        worst.evidence["counterparty_ico"] = worst_ico
    return worst


async def _supplier_rows(
    ico: str, analytics: CompanyAnalytics, graph: GraphStore | None
) -> list[dict]:
    """Per-supplier awarded-value rows for the company as procurer.

    Prefer the graph concentration query; fall back to the analytics partner
    aggregation when Neo4j is not wired (graceful degradation, matching the rest
    of the stack)."""
    if graph is not None:
        result = await graph.supplier_concentration(ico, top_n=_PARTNER_FETCH)
        return result.get("top_suppliers", [])
    partners = await analytics.partners(ico, "supplier", "value", _PARTNER_FETCH, 0)
    return partners.get("items", [])


async def company_risk_profile(
    ico: str, analytics: CompanyAnalytics, graph: GraphStore | None = None
) -> dict:
    """Assemble the red-flag risk profile for a company from ports + domain scoring."""
    core = await analytics.core_stats(ico)
    all_partners = await analytics.partners(ico, "all", "value", _PARTNER_FETCH, 0)
    market = await analytics.market_cpv(_MARKET_CPV_FETCH)
    timeline = await analytics.award_timeline(ico)
    supplier_rows = await _supplier_rows(ico, analytics, graph)

    flags = [
        supplier_concentration(supplier_rows),
        repeat_pair_share(all_partners.get("items", [])),
        market_deviation(core.get("cpv") or [], market),
        _worst_award_cluster(timeline),
    ]
    summary = risk_summary(flags)

    return {
        "ico": ico,
        "risk_score": summary["risk_score"],
        "risk_band": summary["risk_band"],
        "flags": [asdict(f) for f in flags],
        "disclaimer": RISK_DISCLAIMER,
    }
