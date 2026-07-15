"""Pure risk-scoring primitives over domain inputs.

The red-flag engine (plan Phase 4) is the first pure-domain consumer: plain
numbers/rows in, structured flags out, no infrastructure. Every function is fully
testable against the in-memory fakes with zero containers — if anything here needs
to import motor/neo4j the port boundary is wrong (plan §Phase 4 validation gate).

Each flag carries the evidence it was computed from so the /v1 response and MCP
tool can show *why* a company scored the way it did. Thresholds are module
constants with a WHY comment and conservative defaults — over-flagging a paid
compliance product is worse than a miss.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date


def cpv_concentration(values: Sequence[float]) -> tuple[list[float], float]:
    """Herfindahl-Hirschman concentration over CPV spend values.

    Returns ``(shares, hhi)`` where ``shares`` are each value's fraction of the
    positive total (0..1, aligned with the input order) and ``hhi`` is the sum of
    squared shares (0..1, rounded to 4 dp). An empty or all-non-positive input
    yields zeroed shares and an HHI of 0.
    """
    total = sum(v for v in values if v > 0)
    if total <= 0:
        return [0.0 for _ in values], 0.0
    shares = [(v / total if v > 0 else 0.0) for v in values]
    hhi = round(sum(s * s for s in shares), 4)
    return shares, hhi


# --- Thresholds --------------------------------------------------------------

# Supplier-concentration HHI bands. DOJ/EU merger-guideline cutoffs expressed on a
# 0..1 scale (the usual 1500/2500-out-of-10000 divided by 10000).
# WHY: a contracting authority whose spend concentrates on one supplier is the
# canonical single-source-dependency red flag; these are the internationally
# standard, defensible concentration bands.
HHI_MODERATE = 0.15
HHI_HIGH = 0.25

# Repeat-pair value share.
# WHY: >50% of a company's total contract value flowing to/from ONE counterparty
# signals a dominant bilateral relationship worth review. Conservative — framework
# agreements legitimately concentrate value, so we only flag a clear majority; a
# ≥75% share is treated as high severity.
REPEAT_PAIR_VALUE_SHARE = 0.50
REPEAT_PAIR_HIGH_SHARE = 0.75

# Market deviation.
# WHY: an average contract value ≥3× the CPV-market average is a pricing/outlier
# signal (possible overpricing or CPV misclassification). Require a minimum market
# sample per CPV so thin categories don't manufacture noise multiples.
MARKET_DEVIATION_MULTIPLE = 3.0
MARKET_MIN_CONTRACTS = 5

# Award clustering.
# WHY: ≥4 awards to the same counterparty inside 30 days can indicate contract
# splitting to stay below the zákon 343/2015 procedure thresholds. Conservative
# window/count so ordinary repeat business isn't flagged.
AWARD_CLUSTER_COUNT = 4
AWARD_CLUSTER_WINDOW_DAYS = 30

# Overall summary weights — a weighted blend of the individual flag intensities.
# WHY: concentration and single-pair dependency are the strongest standalone
# signals; award clustering is the weakest (repeat business is often legitimate),
# so it weighs least. Weights sum to 1 so the blend is a 0..100 weighted average.
FLAG_WEIGHTS = {
    "supplier_concentration": 0.30,
    "repeat_pair_share": 0.25,
    "market_deviation": 0.25,
    "award_clustering": 0.20,
}

# Overall 0-100 → risk band. Mirrors the HHI band spirit.
RISK_BAND_MODERATE = 30.0
RISK_BAND_HIGH = 60.0


@dataclass
class RiskFlag:
    """One red-flag result: whether it fired, how strong, and the evidence used."""

    code: str
    triggered: bool
    severity: str  # "low" | "moderate" | "high"
    score: float  # 0-100 intensity of this flag (feeds the weighted summary)
    summary: str
    evidence: dict = field(default_factory=dict)


def _band(value: float, moderate: float, high: float) -> str:
    if value >= high:
        return "high"
    if value >= moderate:
        return "moderate"
    return "low"


def _parse_date(value: str | None) -> date | None:
    """Parse the leading ``YYYY-MM-DD`` of a date string; None on anything else."""
    if not value or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def supplier_concentration(procurer_rows: Sequence[dict]) -> RiskFlag:
    """HHI over a procurer's per-supplier awarded-value shares + risk band.

    ``procurer_rows`` are per-supplier aggregates for one contracting authority;
    each row carries ``total_value`` plus an ``ico``/``supplier_ico`` and
    ``name``/``supplier_name`` (tolerating both the analytics-partners and the
    graph shapes). Reuses :func:`cpv_concentration` for the HHI math.
    """
    values = [float(r.get("total_value") or 0.0) for r in procurer_rows]
    shares, hhi = cpv_concentration(values)
    band = _band(hhi, HHI_MODERATE, HHI_HIGH)

    top_supplier: dict | None = None
    if procurer_rows and any(s > 0 for s in shares):
        idx = max(range(len(shares)), key=lambda i: shares[i])
        row = procurer_rows[idx]
        top_supplier = {
            "ico": row.get("ico") or row.get("supplier_ico"),
            "name": row.get("name") or row.get("supplier_name"),
            "value_share": round(shares[idx], 4),
        }

    return RiskFlag(
        code="supplier_concentration",
        triggered=hhi >= HHI_HIGH,
        severity=band,
        score=round(hhi * 100, 1),
        summary=f"Supplier-spend concentration HHI {hhi:.2f} ({band}).",
        evidence={
            "hhi": hhi,
            "supplier_count": sum(1 for v in values if v > 0),
            "top_supplier": top_supplier,
        },
    )


def repeat_pair_share(pair_rows: Sequence[dict]) -> RiskFlag:
    """Share of a company's contract value/count concentrated on one counterparty.

    ``pair_rows`` are the company's counterparties (both roles), each with
    ``total_value``/``contract_count`` and an ``ico``/``name``. Flags when the
    single largest counterparty exceeds :data:`REPEAT_PAIR_VALUE_SHARE` of total
    value.
    """
    total_value = sum(float(r.get("total_value") or 0.0) for r in pair_rows)
    total_count = sum(int(r.get("contract_count") or 0) for r in pair_rows)
    if not pair_rows or total_value <= 0:
        return RiskFlag(
            code="repeat_pair_share",
            triggered=False,
            severity="low",
            score=0.0,
            summary="No counterparty concentration (insufficient data).",
            evidence={"counterparty_count": len(pair_rows)},
        )

    top = max(pair_rows, key=lambda r: float(r.get("total_value") or 0.0))
    value_share = float(top.get("total_value") or 0.0) / total_value
    count_share = (int(top.get("contract_count") or 0) / total_count) if total_count else 0.0
    band = _band(value_share, REPEAT_PAIR_VALUE_SHARE, REPEAT_PAIR_HIGH_SHARE)

    return RiskFlag(
        code="repeat_pair_share",
        triggered=value_share >= REPEAT_PAIR_VALUE_SHARE,
        severity=band,
        score=round(value_share * 100, 1),
        summary=(
            f"{value_share * 100:.0f}% of contract value with a single counterparty ({band})."
        ),
        evidence={
            "counterparty_count": len(pair_rows),
            "top_counterparty": {
                "ico": top.get("ico"),
                "name": top.get("name"),
                "role": top.get("role"),
                "value_share": round(value_share, 4),
                "count_share": round(count_share, 4),
            },
        },
    )


def market_deviation(company_cpv_rows: Sequence[dict], market_cpv_rows: Sequence[dict]) -> RiskFlag:
    """Company's per-CPV average contract value vs. the CPV-market average.

    Both inputs are ``{"_id": cpv_code, "count": n, "total": value}`` rows (the
    ``core_stats`` cpv facet and ``market_cpv`` aggregation). Reports the worst
    multiple across the CPVs the company operates in, ignoring market CPVs with
    fewer than :data:`MARKET_MIN_CONTRACTS` contracts (thin-market guard).
    """
    market_avg: dict[str, float] = {}
    for r in market_cpv_rows:
        code = r.get("_id")
        count = int(r.get("count") or 0)
        total = float(r.get("total") or 0.0)
        if code and count >= MARKET_MIN_CONTRACTS and total > 0:
            market_avg[code] = total / count

    deviations: list[dict] = []
    for r in company_cpv_rows:
        code = r.get("_id")
        count = int(r.get("count") or 0)
        total = float(r.get("total") or 0.0)
        if not code or count <= 0 or code not in market_avg:
            continue
        company_avg = total / count
        multiple = company_avg / market_avg[code]
        deviations.append(
            {
                "cpv_code": code,
                "company_avg": round(company_avg, 2),
                "market_avg": round(market_avg[code], 2),
                "multiple": round(multiple, 2),
            }
        )

    worst = max(deviations, key=lambda d: d["multiple"], default=None)
    multiple = worst["multiple"] if worst else 0.0
    triggered = multiple >= MARKET_DEVIATION_MULTIPLE
    # Threshold multiple → 50; twice the threshold → capped at 100.
    score = round(min(100.0, multiple / MARKET_DEVIATION_MULTIPLE * 50.0), 1) if worst else 0.0
    severity = (
        "high"
        if multiple >= 2 * MARKET_DEVIATION_MULTIPLE
        else ("moderate" if triggered else "low")
    )

    summary = (
        f"Avg contract value {multiple:.1f}× the CPV-market average ({severity})."
        if worst
        else "No comparable CPV market data."
    )
    return RiskFlag(
        code="market_deviation",
        triggered=triggered,
        severity=severity,
        score=score,
        summary=summary,
        evidence={"worst": worst, "compared_cpv_count": len(deviations)},
    )


def award_clustering(dates: Sequence[str]) -> RiskFlag:
    """Largest burst of awards falling inside a :data:`AWARD_CLUSTER_WINDOW_DAYS` window.

    ``dates`` are the award dates of one company↔counterparty series. Flags when
    the densest window holds at least :data:`AWARD_CLUSTER_COUNT` awards — a
    contract-splitting signal. The caller is responsible for grouping by
    counterparty and keeping the worst series.
    """
    parsed = sorted(d for d in (_parse_date(x) for x in dates) if d is not None)
    max_burst = 1 if parsed else 0
    window: tuple[str, str] | None = None

    left = 0
    for right in range(len(parsed)):
        while (parsed[right] - parsed[left]).days > AWARD_CLUSTER_WINDOW_DAYS:
            left += 1
        span = right - left + 1
        if span > max_burst:
            max_burst = span
            window = (parsed[left].isoformat(), parsed[right].isoformat())

    triggered = max_burst >= AWARD_CLUSTER_COUNT
    # Threshold count → 60; twice the threshold → capped at 100.
    score = round(min(100.0, max_burst / AWARD_CLUSTER_COUNT * 60.0), 1) if parsed else 0.0
    severity = (
        "high" if max_burst >= 2 * AWARD_CLUSTER_COUNT else ("moderate" if triggered else "low")
    )

    return RiskFlag(
        code="award_clustering",
        triggered=triggered,
        severity=severity,
        score=score,
        summary=(
            f"{max_burst} awards within {AWARD_CLUSTER_WINDOW_DAYS} days ({severity})."
            if parsed
            else "No dated awards to assess."
        ),
        evidence={
            "max_awards_in_window": max_burst,
            "window_days": AWARD_CLUSTER_WINDOW_DAYS,
            "window": window,
            "total_awards": len(parsed),
        },
    )


def risk_summary(flags: Sequence[RiskFlag]) -> dict:
    """Blend individual flags into an overall 0-100 score + band + triggered list."""
    total_weight = 0.0
    accumulated = 0.0
    for flag in flags:
        weight = FLAG_WEIGHTS.get(flag.code, 0.0)
        total_weight += weight
        accumulated += weight * flag.score
    score = round(accumulated / total_weight, 1) if total_weight else 0.0
    return {
        "risk_score": score,
        "risk_band": _band(score, RISK_BAND_MODERATE, RISK_BAND_HIGH),
        "triggered_flags": [f.code for f in flags if f.triggered],
    }
