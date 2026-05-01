# src/uvo_api/routers/analytics.py
"""Analytics endpoints: period summaries and executive summary for procurers/suppliers."""

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from uvo_api.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

_CPV_LABELS: dict[str, dict[str, str]] = {}


def _load_cpv_labels() -> dict[str, dict[str, str]]:
    global _CPV_LABELS
    if not _CPV_LABELS:
        path = Path(__file__).parent.parent / "data" / "cpv_labels.json"
        _CPV_LABELS = json.loads(path.read_text(encoding="utf-8"))
    return _CPV_LABELS


def _cpv_prefix(code: str | None) -> str:
    if not code:
        return "00000000"
    digits = code.replace("-", "").replace(" ", "")[:8]
    return digits.ljust(8, "0")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

AnomalySeverity = Literal["info", "warn", "critical"]


class PeriodWindow(BaseModel):
    date_from: date
    date_to: date
    prior_date_from: date
    prior_date_to: date


class KpiDeltas(BaseModel):
    total_value_pct: float | None
    contract_count_pct: float | None
    avg_value_pct: float | None
    unique_counterparties_pct: float | None


class PeriodKpis(BaseModel):
    total_value: float
    contract_count: int
    avg_value: float
    unique_counterparties: int
    value_coverage: float
    deltas: KpiDeltas


class MonthBucket(BaseModel):
    month: str  # "YYYY-MM"
    total_value: float
    contract_count: int


class CounterpartyRow(BaseModel):
    ico: str | None
    name: str
    total_value: float
    contract_count: int
    share_pct: float


class CpvRow(BaseModel):
    cpv_code: str
    label_sk: str | None
    label_en: str | None
    total_value: float
    contract_count: int
    share_pct: float


class Concentration(BaseModel):
    hhi: float
    top1_share_pct: float
    top3_share_pct: float


class PeriodSummary(BaseModel):
    ico: str
    name: str
    entity_type: Literal["procurer", "supplier"]
    period: PeriodWindow
    kpis: PeriodKpis
    monthly_spend: list[MonthBucket]
    top_counterparties: list[CounterpartyRow]
    cpv_breakdown: list[CpvRow]
    concentration: Concentration


class Anomaly(BaseModel):
    code: str
    severity: AnomalySeverity
    title_sk: str
    detail_sk: str
    metric_value: float | None


class ExecutiveSummary(PeriodSummary):
    anomalies: list[Anomaly]


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _default_window(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = date.today()
    d_to = date_to or today
    d_from = date_from or (d_to - timedelta(days=365))
    return d_from, d_to


def _prior_window(d_from: date, d_to: date) -> tuple[date, date]:
    length = (d_to - d_from).days
    prior_to = d_from - timedelta(days=1)
    prior_from = prior_to - timedelta(days=length)
    return prior_from, prior_to


def _pct_change(current: float, prior: float) -> float | None:
    if prior == 0:
        return None
    return round((current - prior) / prior * 100, 2)


def _hhi(shares: list[float]) -> float:
    """HHI in 0-1 scale from a list of 0-1 share values."""
    if not shares:
        return 0.0
    return round(sum(s * s for s in shares), 6)


async def _aggregate_procurer(
    ico: str,
    d_from: date,
    d_to: date,
) -> dict:
    """Run Mongo aggregation for a procurer over the given date range.

    Returns a dict with keys: total_value, contract_count, value_with_amount,
    counterparties (dict ico->{"name","value","count"}),
    cpv_buckets (dict code->{"value","count"}),
    monthly (dict "YYYY-MM"->{"value","count"}).
    """
    db = get_db()
    pipeline = [
        {
            "$match": {
                "procurer.ico": ico,
                "publication_date": {
                    "$gte": d_from.isoformat(),
                    "$lte": d_to.isoformat(),
                },
            }
        },
        {
            "$facet": {
                "totals": [
                    {
                        "$group": {
                            "_id": None,
                            "total_value": {
                                "$sum": {
                                    "$ifNull": ["$final_value", {"$ifNull": ["$estimated_value", 0]}]
                                }
                            },
                            "contract_count": {"$sum": 1},
                            "value_with_amount": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$or": [
                                                {"$gt": ["$final_value", None]},
                                                {"$gt": ["$estimated_value", None]},
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    }
                ],
                "counterparties": [
                    {"$unwind": {"path": "$awards", "preserveNullAndEmptyArrays": False}},
                    {
                        "$group": {
                            "_id": "$awards.supplier.ico",
                            "name": {"$first": "$awards.supplier.name"},
                            "total_value": {
                                "$sum": {
                                    "$ifNull": [
                                        "$awards.value",
                                        {
                                            "$divide": [
                                                {
                                                    "$ifNull": [
                                                        "$final_value",
                                                        {"$ifNull": ["$estimated_value", 0]},
                                                    ]
                                                },
                                                {"$max": [{"$size": {"$ifNull": ["$awards", [None]]}}, 1]},
                                            ]
                                        },
                                    ]
                                }
                            },
                            "contract_count": {"$sum": 1},
                        }
                    },
                ],
                "cpv_buckets": [
                    {
                        "$group": {
                            "_id": "$cpv_code",
                            "total_value": {
                                "$sum": {
                                    "$ifNull": ["$final_value", {"$ifNull": ["$estimated_value", 0]}]
                                }
                            },
                            "contract_count": {"$sum": 1},
                        }
                    }
                ],
                "monthly": [
                    {
                        "$group": {
                            "_id": {"$substr": ["$publication_date", 0, 7]},
                            "total_value": {
                                "$sum": {
                                    "$ifNull": ["$final_value", {"$ifNull": ["$estimated_value", 0]}]
                                }
                            },
                            "contract_count": {"$sum": 1},
                        }
                    }
                ],
            }
        },
    ]

    cursor = db["notices"].aggregate(pipeline)
    results = await cursor.to_list(length=1)
    return results[0] if results else {}


async def _aggregate_supplier(
    ico: str,
    d_from: date,
    d_to: date,
) -> dict:
    """Run Mongo aggregation for a supplier over the given date range."""
    db = get_db()
    pipeline = [
        {
            "$match": {
                "awards": {"$elemMatch": {"supplier.ico": ico}},
                "publication_date": {
                    "$gte": d_from.isoformat(),
                    "$lte": d_to.isoformat(),
                },
            }
        },
        {"$addFields": {"_matching_awards": {"$filter": {
            "input": "$awards",
            "as": "a",
            "cond": {"$eq": ["$$a.supplier.ico", ico]},
        }}}},
        {
            "$facet": {
                "totals": [
                    {
                        "$group": {
                            "_id": None,
                            "total_value": {
                                "$sum": {
                                    "$reduce": {
                                        "input": "$_matching_awards",
                                        "initialValue": 0,
                                        "in": {
                                            "$add": [
                                                "$$value",
                                                {
                                                    "$ifNull": [
                                                        "$$this.value",
                                                        {
                                                            "$divide": [
                                                                {
                                                                    "$ifNull": [
                                                                        "$final_value",
                                                                        {
                                                                            "$ifNull": [
                                                                                "$estimated_value",
                                                                                0,
                                                                            ]
                                                                        },
                                                                    ]
                                                                },
                                                                {"$max": [{"$size": {"$ifNull": ["$awards", [None]]}}, 1]},
                                                            ]
                                                        },
                                                    ]
                                                },
                                            ]
                                        },
                                    }
                                }
                            },
                            "contract_count": {"$sum": 1},
                            "value_with_amount": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$or": [
                                                {"$gt": ["$final_value", None]},
                                                {"$gt": ["$estimated_value", None]},
                                                {
                                                    "$gt": [
                                                        {
                                                            "$size": {
                                                                "$filter": {
                                                                    "input": "$_matching_awards",
                                                                    "as": "a",
                                                                    "cond": {"$gt": ["$$a.value", None]},
                                                                }
                                                            }
                                                        },
                                                        0,
                                                    ]
                                                },
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    }
                ],
                "counterparties": [
                    {
                        "$group": {
                            "_id": "$procurer.ico",
                            "name": {"$first": "$procurer.name"},
                            "total_value": {
                                "$sum": {
                                    "$reduce": {
                                        "input": "$_matching_awards",
                                        "initialValue": 0,
                                        "in": {
                                            "$add": [
                                                "$$value",
                                                {
                                                    "$ifNull": [
                                                        "$$this.value",
                                                        {
                                                            "$divide": [
                                                                {
                                                                    "$ifNull": [
                                                                        "$final_value",
                                                                        {
                                                                            "$ifNull": [
                                                                                "$estimated_value",
                                                                                0,
                                                                            ]
                                                                        },
                                                                    ]
                                                                },
                                                                {"$max": [{"$size": {"$ifNull": ["$awards", [None]]}}, 1]},
                                                            ]
                                                        },
                                                    ]
                                                },
                                            ]
                                        },
                                    }
                                }
                            },
                            "contract_count": {"$sum": 1},
                        }
                    }
                ],
                "cpv_buckets": [
                    {
                        "$group": {
                            "_id": "$cpv_code",
                            "total_value": {
                                "$sum": {
                                    "$reduce": {
                                        "input": "$_matching_awards",
                                        "initialValue": 0,
                                        "in": {
                                            "$add": [
                                                "$$value",
                                                {
                                                    "$ifNull": [
                                                        "$$this.value",
                                                        {
                                                            "$divide": [
                                                                {
                                                                    "$ifNull": [
                                                                        "$final_value",
                                                                        {
                                                                            "$ifNull": [
                                                                                "$estimated_value",
                                                                                0,
                                                                            ]
                                                                        },
                                                                    ]
                                                                },
                                                                {"$max": [{"$size": {"$ifNull": ["$awards", [None]]}}, 1]},
                                                            ]
                                                        },
                                                    ]
                                                },
                                            ]
                                        },
                                    }
                                }
                            },
                            "contract_count": {"$sum": 1},
                        }
                    }
                ],
                "monthly": [
                    {
                        "$group": {
                            "_id": {"$substr": ["$publication_date", 0, 7]},
                            "total_value": {
                                "$sum": {
                                    "$reduce": {
                                        "input": "$_matching_awards",
                                        "initialValue": 0,
                                        "in": {
                                            "$add": [
                                                "$$value",
                                                {
                                                    "$ifNull": [
                                                        "$$this.value",
                                                        {
                                                            "$divide": [
                                                                {
                                                                    "$ifNull": [
                                                                        "$final_value",
                                                                        {
                                                                            "$ifNull": [
                                                                                "$estimated_value",
                                                                                0,
                                                                            ]
                                                                        },
                                                                    ]
                                                                },
                                                                {"$max": [{"$size": {"$ifNull": ["$awards", [None]]}}, 1]},
                                                            ]
                                                        },
                                                    ]
                                                },
                                            ]
                                        },
                                    }
                                }
                            },
                            "contract_count": {"$sum": 1},
                        }
                    }
                ],
            }
        },
    ]

    cursor = db["notices"].aggregate(pipeline)
    results = await cursor.to_list(length=1)
    return results[0] if results else {}


def _build_period_summary(
    ico: str,
    name: str,
    entity_type: Literal["procurer", "supplier"],
    period: PeriodWindow,
    cur: dict,
    prior: dict,
) -> PeriodSummary:
    labels = _load_cpv_labels()

    # -- current period KPIs --
    cur_totals = (cur.get("totals") or [{}])[0]
    total_value = float(cur_totals.get("total_value") or 0)
    contract_count = int(cur_totals.get("contract_count") or 0)
    value_with_amount = int(cur_totals.get("value_with_amount") or 0)
    avg_value = total_value / contract_count if contract_count else 0.0
    value_coverage = value_with_amount / contract_count if contract_count else 0.0

    # unique counterparties
    cur_cp_raw = cur.get("counterparties") or []
    unique_counterparties = len(cur_cp_raw)

    # -- prior period KPIs --
    prior_totals = (prior.get("totals") or [{}])[0]
    prior_total_value = float(prior_totals.get("total_value") or 0)
    prior_contract_count = int(prior_totals.get("contract_count") or 0)
    prior_avg_value = prior_total_value / prior_contract_count if prior_contract_count else 0.0
    prior_cp_raw = prior.get("counterparties") or []
    prior_unique_cp = len(prior_cp_raw)

    deltas = KpiDeltas(
        total_value_pct=_pct_change(total_value, prior_total_value),
        contract_count_pct=_pct_change(float(contract_count), float(prior_contract_count)),
        avg_value_pct=_pct_change(avg_value, prior_avg_value),
        unique_counterparties_pct=_pct_change(float(unique_counterparties), float(prior_unique_cp)),
    )

    kpis = PeriodKpis(
        total_value=total_value,
        contract_count=contract_count,
        avg_value=avg_value,
        unique_counterparties=unique_counterparties,
        value_coverage=round(value_coverage, 4),
        deltas=deltas,
    )

    # -- monthly spend --
    monthly_raw = cur.get("monthly") or []
    monthly_spend = sorted(
        [
            MonthBucket(
                month=m["_id"] or "",
                total_value=float(m.get("total_value") or 0),
                contract_count=int(m.get("contract_count") or 0),
            )
            for m in monthly_raw
            if m.get("_id")
        ],
        key=lambda x: x.month,
    )

    # -- top counterparties --
    cp_sorted = sorted(cur_cp_raw, key=lambda x: float(x.get("total_value") or 0), reverse=True)
    cp_total = sum(float(x.get("total_value") or 0) for x in cp_sorted)
    top_counterparties = [
        CounterpartyRow(
            ico=row.get("_id"),
            name=row.get("name") or "",
            total_value=float(row.get("total_value") or 0),
            contract_count=int(row.get("contract_count") or 0),
            share_pct=round(float(row.get("total_value") or 0) / cp_total, 4) if cp_total else 0.0,
        )
        for row in cp_sorted[:10]
    ]

    # -- CPV breakdown (top 10 + Other) --
    cpv_raw = sorted(
        cur.get("cpv_buckets") or [], key=lambda x: float(x.get("total_value") or 0), reverse=True
    )
    cpv_total = sum(float(x.get("total_value") or 0) for x in cpv_raw)
    cpv_top = cpv_raw[:10]
    cpv_rest = cpv_raw[10:]

    cpv_rows: list[CpvRow] = []
    for bucket in cpv_top:
        raw_code = bucket.get("_id") or ""
        code = _cpv_prefix(raw_code)
        label = labels.get(code, {})
        cpv_rows.append(
            CpvRow(
                cpv_code=code,
                label_sk=label.get("sk"),
                label_en=label.get("en"),
                total_value=float(bucket.get("total_value") or 0),
                contract_count=int(bucket.get("contract_count") or 0),
                share_pct=round(float(bucket.get("total_value") or 0) / cpv_total, 4)
                if cpv_total
                else 0.0,
            )
        )
    if cpv_rest:
        rest_value = sum(float(x.get("total_value") or 0) for x in cpv_rest)
        rest_count = sum(int(x.get("contract_count") or 0) for x in cpv_rest)
        cpv_rows.append(
            CpvRow(
                cpv_code="other",
                label_sk="Ostatné",
                label_en="Other",
                total_value=rest_value,
                contract_count=rest_count,
                share_pct=round(rest_value / cpv_total, 4) if cpv_total else 0.0,
            )
        )

    # -- concentration --
    if cp_total > 0:
        shares = [float(x.get("total_value") or 0) / cp_total for x in cp_sorted]
    else:
        shares = []

    hhi = _hhi(shares)
    top1 = shares[0] if shares else 0.0
    top3 = sum(shares[:3])

    concentration = Concentration(
        hhi=hhi,
        top1_share_pct=round(top1, 4),
        top3_share_pct=round(top3, 4),
    )

    return PeriodSummary(
        ico=ico,
        name=name,
        entity_type=entity_type,
        period=period,
        kpis=kpis,
        monthly_spend=monthly_spend,
        top_counterparties=top_counterparties,
        cpv_breakdown=cpv_rows,
        concentration=concentration,
    )


def _detect_anomalies(
    summary: PeriodSummary,
    prior: dict,
) -> list[Anomaly]:
    anomalies: list[Anomaly] = []
    entity_word = "dodávateľ" if summary.entity_type == "procurer" else "odberateľ"

    # Rule 1: single counterparty dominance
    top1 = summary.concentration.top1_share_pct
    if top1 >= 0.7:
        anomalies.append(
            Anomaly(
                code="single_counterparty_dominance",
                severity="warn",
                title_sk=f"Jeden {entity_word} získal viac ako 70% objemu",
                detail_sk=f"Podiel najväčšieho {entity_word}a je {round(top1 * 100, 1)}%.",
                metric_value=round(top1, 4),
            )
        )

    # Rule 2: value spike vs prior (requires prior data)
    pct = summary.kpis.deltas.total_value_pct
    if pct is not None and pct >= 50.0:
        anomalies.append(
            Anomaly(
                code="value_spike_vs_prior",
                severity="info",
                title_sk=f"Objem narástol o {round(pct, 1)}% oproti predchádzajúcemu obdobiu",
                detail_sk=f"Celkový objem zákaziek vzrástol o {round(pct, 1)}%.",
                metric_value=round(pct, 2),
            )
        )

    # Rule 3: HHI jump (requires prior data)
    prior_totals = (prior.get("totals") or [{}])[0]
    prior_contract_count = int(prior_totals.get("contract_count") or 0)
    if prior_contract_count > 0:
        prior_cp_raw = prior.get("counterparties") or []
        prior_cp_total = sum(float(x.get("total_value") or 0) for x in prior_cp_raw)
        if prior_cp_total > 0:
            prior_shares = [float(x.get("total_value") or 0) / prior_cp_total for x in prior_cp_raw]
            prior_hhi = _hhi(prior_shares)
            delta_hhi = summary.concentration.hhi - prior_hhi
            if delta_hhi >= 0.15:
                anomalies.append(
                    Anomaly(
                        code="hhi_jump",
                        severity="warn",
                        title_sk="Koncentrácia partnerov sa výrazne zvýšila",
                        detail_sk=f"HHI vzrástol o {round(delta_hhi, 3)} (z {round(prior_hhi, 3)} na {round(summary.concentration.hhi, 3)}).",
                        metric_value=round(delta_hhi, 4),
                    )
                )

    return anomalies


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/api/procurers/{ico}/period-summary", response_model=PeriodSummary)
async def procurer_period_summary(
    ico: str,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> PeriodSummary:
    d_from, d_to = _default_window(date_from, date_to)
    if d_from > d_to:
        raise HTTPException(status_code=400, detail="date_from must be <= date_to")

    db = get_db()
    entity = await db["procurers"].find_one({"ico": ico})
    if not entity:
        raise HTTPException(status_code=404, detail=f"Procurer {ico} not found")

    name = entity.get("name") or ""
    p_from, p_to = _prior_window(d_from, d_to)
    cur, prior = await _aggregate_procurer(ico, d_from, d_to), await _aggregate_procurer(ico, p_from, p_to)

    period = PeriodWindow(date_from=d_from, date_to=d_to, prior_date_from=p_from, prior_date_to=p_to)
    return _build_period_summary(ico, name, "procurer", period, cur, prior)


@router.get("/api/suppliers/{ico}/period-summary", response_model=PeriodSummary)
async def supplier_period_summary(
    ico: str,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> PeriodSummary:
    d_from, d_to = _default_window(date_from, date_to)
    if d_from > d_to:
        raise HTTPException(status_code=400, detail="date_from must be <= date_to")

    db = get_db()
    entity = await db["suppliers"].find_one({"ico": ico})
    if not entity:
        raise HTTPException(status_code=404, detail=f"Supplier {ico} not found")

    name = entity.get("name") or ""
    p_from, p_to = _prior_window(d_from, d_to)
    cur, prior = await _aggregate_supplier(ico, d_from, d_to), await _aggregate_supplier(ico, p_from, p_to)

    period = PeriodWindow(date_from=d_from, date_to=d_to, prior_date_from=p_from, prior_date_to=p_to)
    return _build_period_summary(ico, name, "supplier", period, cur, prior)


@router.get("/api/companies/{ico}/executive-summary", response_model=ExecutiveSummary)
async def company_executive_summary(
    ico: str,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    entity_type: Literal["procurer", "supplier"] = Query("procurer"),
) -> ExecutiveSummary:
    d_from, d_to = _default_window(date_from, date_to)
    if d_from > d_to:
        raise HTTPException(status_code=400, detail="date_from must be <= date_to")

    db = get_db()
    collection = "procurers" if entity_type == "procurer" else "suppliers"
    entity = await db[collection].find_one({"ico": ico})
    if not entity:
        raise HTTPException(status_code=404, detail=f"{entity_type.capitalize()} {ico} not found")

    name = entity.get("name") or ""
    p_from, p_to = _prior_window(d_from, d_to)

    if entity_type == "procurer":
        cur = await _aggregate_procurer(ico, d_from, d_to)
        prior = await _aggregate_procurer(ico, p_from, p_to)
    else:
        cur = await _aggregate_supplier(ico, d_from, d_to)
        prior = await _aggregate_supplier(ico, p_from, p_to)

    period = PeriodWindow(date_from=d_from, date_to=d_to, prior_date_from=p_from, prior_date_to=p_to)
    base = _build_period_summary(ico, name, entity_type, period, cur, prior)
    anomalies = _detect_anomalies(base, prior)

    return ExecutiveSummary(**base.model_dump(), anomalies=anomalies)
