"""Pure risk-scoring primitives over domain inputs.

The red-flag engine (plan Phase 4) is the first pure-domain consumer: plain
numbers/rows in, structured flags out, no infrastructure. Every function is fully
testable against the in-memory fakes with zero containers — if anything here needs
to import motor/neo4j the port boundary is wrong (plan §Phase 4 validation gate).

Each flag carries the evidence it was computed from so the /v1 response and MCP
tool can show *why* a company scored the way it did. Thresholds are module
constants with a WHY comment and conservative defaults — over-flagging a paid
compliance product is worse than a miss.

Flags are framed as *observations*, never as conclusions or accusations: every
signal has legitimate explanations (framework agreements, dynamic purchasing
systems, specialised thin markets, large investment projects). The summaries
state the measurement and, at most, that it "warrants review"; the response
carries :data:`RISK_DISCLAIMER` making the statistical, non-accusatory nature
explicit. The scoring choices here were confirmed against zákon č. 343/2015 Z. z.
during the domain/legal review.
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


# --- Disclaimer --------------------------------------------------------------

# Attached verbatim to every risk response (/v1 payload + MCP tool) and mirrored
# in docs/api-v1.md. Legal/domain review: the signals are automatically computed
# statistical indicators, NOT assertions of wrongdoing — the disclaimer must ship
# with the data so no consumer reads a flag as an accusation.
RISK_DISCLAIMER = (
    "Upozornenie: Rizikové signály v tomto profile sú automaticky vypočítané "
    "štatistické indikátory z verejne dostupných údajov o verejnom obstarávaní "
    "(Vestník VO, CRZ, TED, ITMS). Nie sú tvrdením ani obvinením z porušenia "
    "zákona č. 343/2015 Z. z., z protiprávneho konania, korupcie ani nekalej "
    "súťaže. Mnohé signály majú legitímne vysvetlenie — najmä rámcové dohody, "
    "dynamické nákupné systémy, špecializované trhy s malým počtom dodávateľov "
    "či veľké investičné projekty. Signály slúžia výhradne ako podnet na ďalšie "
    "overenie a nemožno ich použiť ako jediný podklad pre rozhodnutie o "
    "konkrétnej osobe. Dotknutá osoba môže proti spracúvaniu svojich osobných "
    "údajov namietať."
)


# --- Thresholds --------------------------------------------------------------

# Supplier-concentration HHI bands. DOJ/EU merger-guideline cutoffs expressed on a
# 0..1 scale (the usual 1500/2500-out-of-10000 divided by 10000).
# WHY: a contracting authority whose spend concentrates on one supplier is the
# canonical single-source-dependency observation; these are the internationally
# standard, defensible concentration bands.
HHI_MODERATE = 0.15
HHI_HIGH = 0.25

# Supplier-concentration materiality guard.
# WHY: a high HHI only carries a signal when concentration is a *choice* across a
# real field of suppliers and the spend is material. With fewer than 5 distinct
# suppliers a high HHI is expected (a specialised/thin market simply has few
# vendors) and says nothing, so below the guard we still report the HHI but do not
# trigger and mark the flag informational.
SUPPLIER_CONCENTRATION_MIN_SUPPLIERS = 5
SUPPLIER_CONCENTRATION_MIN_VALUE = 100_000.0

# Repeat-pair value share.
# WHY: >50% of a company's total contract value flowing to/from ONE counterparty
# is a dominant bilateral relationship worth review. Conservative — framework
# agreements legitimately concentrate value, so we only flag a clear majority; a
# ≥75% share is treated as high severity.
REPEAT_PAIR_VALUE_SHARE = 0.50
REPEAT_PAIR_HIGH_SHARE = 0.75

# Repeat-pair materiality guard.
# WHY: a dominant share is only notable across a genuine field of counterparties
# (≥3) and at material value (≥€50k). A firm with one or two counterparties is
# definitionally concentrated and legitimately so; below the guard we report the
# share but do not trigger.
REPEAT_PAIR_MIN_COUNTERPARTIES = 3
REPEAT_PAIR_MIN_VALUE = 50_000.0
# WHY: a supplier depending on a single contracting authority is common and
# legitimate for small firms, so the flag weighs less when the subject sits in the
# supplier role of the dominant pair (its top counterparty is a procurer).
REPEAT_PAIR_SUPPLIER_WEIGHT_FACTOR = 0.5

# Market deviation.
# WHY: an average contract value ≥3× the CPV-market baseline is an atypical-value
# observation (unusually high average, possible CPV misclassification, or simply a
# larger/complex project). Baseline is the per-CPV MEDIAN (robust to a handful of
# very large contracts); require a substantial market sample per CPV so thin
# categories don't manufacture a noise multiple.
MARKET_DEVIATION_MULTIPLE = 3.0
MARKET_MIN_CONTRACTS = 20

# Award clustering.
# WHY: ≥4 awards to the same counterparty inside 30 days is a dense burst. On its
# own it is often ordinary repeat business, so it is only escalated when it also
# shares a CPV division (Guard A) and its summed value approaches a §5 low-value
# ceiling (Guard B) — the shape contract-splitting leaves in the data.
AWARD_CLUSTER_COUNT = 4
AWARD_CLUSTER_WINDOW_DAYS = 30

# §5 low-value contract ceilings, zákon č. 343/2015 Z. z. ("zákazka s nízkou
# hodnotou"). Contract-splitting slices one requirement into several sub-threshold
# awards to stay under the applicable ceiling and avoid a full tender; a dense,
# single-division burst whose summed value sits just below the ceiling is that
# footprint. The four distinct ceilings are listed for the record, but the picker
# is simplified to two (works vs. everything else) because a CPV division alone
# cannot reliably distinguish Annex-1 services or foodstuffs.
LOW_VALUE_CEILING_GOODS_SERVICES = 180_000.0  # tovary a bežné služby
LOW_VALUE_CEILING_WORKS = 300_000.0  # stavebné práce (CPV division 45)
LOW_VALUE_CEILING_ANNEX1_SERVICES = 400_000.0  # Annex 1 (sociálne a osobitné) služby
LOW_VALUE_CEILING_FOODSTUFFS = 215_000.0  # potraviny
LOW_VALUE_FLOOR = 10_000.0  # below this a burst is de-minimis; never escalate
# "approaches the ceiling" = summed burst value within this band of the ceiling
# (from below). Above the ceiling the awards fall outside the low-value regime, so
# a value >1.0× is not the splitting shape and is not escalated.
CEILING_APPROACH_BAND = (0.7, 1.0)

# Procedure-type substrings marking a framework agreement or dynamic purchasing
# system. Call-offs against these legitimately cluster in time and are the known
# false-positive source for award_clustering, so notices carrying them are
# excluded upstream. procedure_type is a free-text field, so this is a lowercased
# substring test rather than an enum match.
_FRAMEWORK_DNS_MARKERS = ("rámc", "framework", "dynamick", "dynamic purchasing", "dns")

# Overall summary weights — a weighted blend of the individual flag intensities.
# WHY: concentration and single-pair dependency are the strongest standalone
# observations; award clustering is the weakest (repeat business is often
# legitimate), so it weighs least. Weights sum to 1 so the blend is a 0..100
# weighted average.
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
    severity: str  # "informational" | "low" | "moderate" | "high"
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


def _cpv_division(code: str | None) -> str | None:
    """The 2-digit CPV division ("division" = first two digits of the CPV code)."""
    return code[:2] if code and len(code) >= 2 else None


def is_framework_or_dns(procedure_type: str | None) -> bool:
    """Whether a procedure_type string marks a framework agreement or DNS call-off."""
    if not procedure_type:
        return False
    text = procedure_type.lower()
    return any(marker in text for marker in _FRAMEWORK_DNS_MARKERS)


def supplier_concentration(procurer_rows: Sequence[dict]) -> RiskFlag:
    """HHI over a procurer's per-supplier awarded-value shares + risk band.

    ``procurer_rows`` are per-supplier aggregates for one contracting authority;
    each row carries ``total_value`` plus an ``ico``/``supplier_ico`` and
    ``name``/``supplier_name`` (tolerating both the analytics-partners and the
    graph shapes). Reuses :func:`cpv_concentration` for the HHI math.

    Only triggers when the concentration is *material* — at least
    :data:`SUPPLIER_CONCENTRATION_MIN_SUPPLIERS` distinct suppliers and
    :data:`SUPPLIER_CONCENTRATION_MIN_VALUE` total value. Below that the HHI is
    still reported (in ``evidence``) but the flag is informational and does not
    feed the blend, since a high HHI over 1–2 vendors is expected, not a signal.
    """
    values = [float(r.get("total_value") or 0.0) for r in procurer_rows]
    shares, hhi = cpv_concentration(values)
    supplier_count = sum(1 for v in values if v > 0)
    total_value = sum(v for v in values if v > 0)

    top_supplier: dict | None = None
    if procurer_rows and any(s > 0 for s in shares):
        idx = max(range(len(shares)), key=lambda i: shares[i])
        row = procurer_rows[idx]
        top_supplier = {
            "ico": row.get("ico") or row.get("supplier_ico"),
            "name": row.get("name") or row.get("supplier_name"),
            "value_share": round(shares[idx], 4),
        }

    material = (
        supplier_count >= SUPPLIER_CONCENTRATION_MIN_SUPPLIERS
        and total_value >= SUPPLIER_CONCENTRATION_MIN_VALUE
    )
    if material:
        severity = _band(hhi, HHI_MODERATE, HHI_HIGH)
        score = round(hhi * 100, 1)
        triggered = hhi >= HHI_HIGH
    else:
        severity = "informational"
        score = 0.0
        triggered = False

    if supplier_count:
        top_pct = round((top_supplier["value_share"] if top_supplier else 0.0) * 100)
        label = "warrants review" if triggered else "informational"
        summary = (
            f"Awarded value spread across {supplier_count} suppliers, top holds "
            f"{top_pct}% (HHI {hhi:.2f}) ({label})."
        )
    else:
        summary = "No supplier spend to assess."

    return RiskFlag(
        code="supplier_concentration",
        triggered=triggered,
        severity=severity,
        score=score,
        summary=summary,
        evidence={
            "hhi": hhi,
            "supplier_count": supplier_count,
            "total_value": round(total_value, 2),
            "top_supplier": top_supplier,
        },
    )


def repeat_pair_share(pair_rows: Sequence[dict]) -> RiskFlag:
    """Share of a company's contract value/count concentrated on one counterparty.

    ``pair_rows`` are the company's counterparties (both roles), each with
    ``total_value``/``contract_count``, an ``ico``/``name`` and a ``role`` (the
    *counterparty's* role). Only triggers when material — at least
    :data:`REPEAT_PAIR_MIN_COUNTERPARTIES` counterparties and
    :data:`REPEAT_PAIR_MIN_VALUE` total value — and the single largest counterparty
    exceeds :data:`REPEAT_PAIR_VALUE_SHARE` of total value. ``evidence.subject_role``
    records whether the subject sits in the supplier or procurer role of the
    dominant pair, which :func:`risk_summary` uses to down-weight supplier-side
    dependency.
    """
    total_value = sum(float(r.get("total_value") or 0.0) for r in pair_rows)
    total_count = sum(int(r.get("contract_count") or 0) for r in pair_rows)
    counterparty_count = len(pair_rows)
    if not pair_rows or total_value <= 0:
        return RiskFlag(
            code="repeat_pair_share",
            triggered=False,
            severity="informational",
            score=0.0,
            summary="No counterparty concentration (insufficient data).",
            evidence={"counterparty_count": counterparty_count, "subject_role": None},
        )

    top = max(pair_rows, key=lambda r: float(r.get("total_value") or 0.0))
    value_share = float(top.get("total_value") or 0.0) / total_value
    count_share = (int(top.get("contract_count") or 0) / total_count) if total_count else 0.0
    # The counterparty's role is the mirror of the subject's role in this pair.
    top_role = top.get("role")
    subject_role = (
        "supplier" if top_role == "procurer" else ("procurer" if top_role == "supplier" else None)
    )

    material = (
        counterparty_count >= REPEAT_PAIR_MIN_COUNTERPARTIES
        and total_value >= REPEAT_PAIR_MIN_VALUE
    )
    if material:
        severity = _band(value_share, REPEAT_PAIR_VALUE_SHARE, REPEAT_PAIR_HIGH_SHARE)
        score = round(value_share * 100, 1)
        triggered = value_share >= REPEAT_PAIR_VALUE_SHARE
    else:
        severity = "informational"
        score = 0.0
        triggered = False

    label = "warrants review" if triggered else "informational"
    return RiskFlag(
        code="repeat_pair_share",
        triggered=triggered,
        severity=severity,
        score=score,
        summary=(
            f"{value_share * 100:.0f}% of contract value concentrated with a single "
            f"counterparty across {counterparty_count} partners ({label})."
        ),
        evidence={
            "counterparty_count": counterparty_count,
            "total_value": round(total_value, 2),
            "subject_role": subject_role,
            "top_counterparty": {
                "ico": top.get("ico"),
                "name": top.get("name"),
                "role": top_role,
                "value_share": round(value_share, 4),
                "count_share": round(count_share, 4),
            },
        },
    )


def market_deviation(company_cpv_rows: Sequence[dict], market_cpv_rows: Sequence[dict]) -> RiskFlag:
    """Company's per-CPV average contract value vs. the CPV-market MEDIAN.

    Both inputs are ``{"_id": cpv_code, "count": n, "total": value}`` rows (the
    ``core_stats`` cpv facet and ``market_cpv`` aggregation) grouped at the finest
    available granularity — the full CPV code. ``market_cpv_rows`` additionally
    carry ``median`` (the per-CPV median contract value); when it is absent the
    mean (``total/count``) is used as a fallback baseline. Reports the worst
    multiple across the CPVs the company operates in, ignoring market CPVs with
    fewer than :data:`MARKET_MIN_CONTRACTS` contracts (thin-market guard).
    """
    market_baseline: dict[str, float] = {}
    for r in market_cpv_rows:
        code = r.get("_id")
        count = int(r.get("count") or 0)
        total = float(r.get("total") or 0.0)
        if not code or count < MARKET_MIN_CONTRACTS:
            continue
        median = r.get("median")
        # Prefer the median (robust to a few very large contracts); fall back to
        # the mean when the aggregation didn't supply one (older adapter/DB).
        if median is not None and float(median) > 0:
            baseline = float(median)
        elif total > 0:
            baseline = total / count
        else:
            continue
        market_baseline[code] = baseline

    deviations: list[dict] = []
    for r in company_cpv_rows:
        code = r.get("_id")
        count = int(r.get("count") or 0)
        total = float(r.get("total") or 0.0)
        if not code or count <= 0 or code not in market_baseline:
            continue
        company_avg = total / count
        multiple = company_avg / market_baseline[code]
        deviations.append(
            {
                "cpv_code": code,
                "company_avg": round(company_avg, 2),
                "market_baseline": round(market_baseline[code], 2),
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
        f"Average contract value {multiple:.1f}× the CPV market median "
        f"({'atypical value' if triggered else 'within normal range'})."
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


def award_clustering(awards: Sequence[dict]) -> RiskFlag:
    """Densest burst of awards inside a :data:`AWARD_CLUSTER_WINDOW_DAYS` window.

    ``awards`` are one company↔counterparty series, each a
    ``{"date", "cpv_code", "value"}`` dict. The caller groups by counterparty
    (guaranteeing a single procurer/counterparty per series) and keeps the worst
    series. A dense burst is only *escalated* to triggered when Guard A holds — the
    burst shares a single CPV division — since mixed-division activity is ordinary
    diverse business, not a splitting footprint. When it shares a division and its
    summed value approaches a §5 low-value ceiling (Guard B,
    :data:`CEILING_APPROACH_BAND`), severity is raised to high. Without a shared
    division the flag reports neutral "award frequency" at lower severity and does
    not trigger.
    """
    records = sorted(
        (
            (_parse_date(a.get("date")), a.get("cpv_code"), float(a.get("value") or 0.0))
            for a in awards
        ),
        key=lambda r: (r[0] is None, r[0]),
    )
    records = [r for r in records if r[0] is not None]
    n = len(records)
    max_burst = 1 if records else 0
    best: tuple[int, int] | None = None

    left = 0
    for right in range(n):
        while (records[right][0] - records[left][0]).days > AWARD_CLUSTER_WINDOW_DAYS:
            left += 1
        span = right - left + 1
        if span > max_burst:
            max_burst = span
            best = (left, right)

    if best is not None:
        burst = records[best[0] : best[1] + 1]
    else:
        burst = records[:1]
    window = (burst[0][0].isoformat(), burst[-1][0].isoformat()) if best else None
    window_value = sum(v for _, _, v in burst)
    divisions = {_cpv_division(c) for _, c, _ in burst if _cpv_division(c)}
    shared_division = len(divisions) == 1
    cluster_division = next(iter(divisions)) if shared_division else None

    dense = max_burst >= AWARD_CLUSTER_COUNT
    triggered = dense and shared_division  # Guard A gates triggering.
    # Threshold count → 60; twice the threshold → capped at 100.
    base_score = round(min(100.0, max_burst / AWARD_CLUSTER_COUNT * 60.0), 1) if records else 0.0

    ceiling = (
        LOW_VALUE_CEILING_WORKS if cluster_division == "45" else LOW_VALUE_CEILING_GOODS_SERVICES
    )
    lo, hi = CEILING_APPROACH_BAND
    approaches_ceiling = (
        triggered
        and window_value >= LOW_VALUE_FLOOR
        and lo * ceiling <= window_value <= hi * ceiling
    )

    if not dense:
        severity = "low"
        score = base_score
    elif not shared_division:
        # Guard A not met: neutral award frequency, don't escalate.
        severity = "informational"
        score = round(base_score * 0.5, 1)
    elif approaches_ceiling or max_burst >= 2 * AWARD_CLUSTER_COUNT:
        severity = "high"
        score = base_score
    else:
        severity = "moderate"
        score = base_score

    if not records:
        summary = "No dated awards to assess."
    elif not dense:
        summary = (
            f"{max_burst} awards to the same counterparty within a "
            f"{AWARD_CLUSTER_WINDOW_DAYS}-day window (award frequency)."
        )
    elif not shared_division:
        summary = (
            f"{max_burst} awards to the same counterparty within a "
            f"{AWARD_CLUSTER_WINDOW_DAYS}-day window across mixed CPV divisions "
            "(award frequency)."
        )
    else:
        ceiling_note = (
            f", summed value €{window_value:,.0f} near the €{ceiling:,.0f} low-value ceiling"
            if approaches_ceiling
            else ""
        )
        summary = (
            f"{max_burst} awards to the same counterparty within a "
            f"{AWARD_CLUSTER_WINDOW_DAYS}-day window sharing CPV division "
            f"{cluster_division}{ceiling_note} (warrants review)."
        )

    return RiskFlag(
        code="award_clustering",
        triggered=triggered,
        severity=severity,
        score=score,
        summary=summary,
        evidence={
            "max_awards_in_window": max_burst,
            "window_days": AWARD_CLUSTER_WINDOW_DAYS,
            "window": window,
            "window_value": round(window_value, 2),
            "shared_cpv_division": cluster_division,
            "approaches_low_value_ceiling": approaches_ceiling,
            "total_awards": n,
        },
    )


def risk_summary(flags: Sequence[RiskFlag]) -> dict:
    """Blend individual flags into an overall 0-100 score + band + triggered list.

    ``repeat_pair_share`` is down-weighted by
    :data:`REPEAT_PAIR_SUPPLIER_WEIGHT_FACTOR` when its ``evidence.subject_role`` is
    ``"supplier"`` — a small supplier depending on one contracting authority is
    common and legitimate, so it should influence the blend less.
    """
    total_weight = 0.0
    accumulated = 0.0
    for flag in flags:
        weight = FLAG_WEIGHTS.get(flag.code, 0.0)
        if flag.code == "repeat_pair_share" and flag.evidence.get("subject_role") == "supplier":
            weight *= REPEAT_PAIR_SUPPLIER_WEIGHT_FACTOR
        total_weight += weight
        accumulated += weight * flag.score
    score = round(accumulated / total_weight, 1) if total_weight else 0.0
    return {
        "risk_score": score,
        "risk_band": _band(score, RISK_BAND_MODERATE, RISK_BAND_HIGH),
        "triggered_flags": [f.code for f in flags if f.triggered],
    }
