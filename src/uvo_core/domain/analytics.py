"""Analytics dashboard domain: filter value object, D1 constants and pure helpers.

Metric definition **D1** (spec 2026-10-19 §4): a contract is a ``contract_award``
notice, its value is ``final_value`` then ``estimated_value`` then 0, and its date
is ``award_date`` then ``publication_date``. Everything here is I/O free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, timedelta

from uvo_core.domain.cpv import cpv_prefix

D1_NOTICE_TYPE = "contract_award"
# final_value -> estimated_value -> 0  (mirrors uvo_api._schema.contract_value)
VALUE_EXPR: dict = {"$ifNull": ["$final_value", {"$ifNull": ["$estimated_value", 0]}]}
# award_date -> publication_date  (mirrors uvo_api._schema.contract_date)
DATE_EXPR: dict = {"$ifNull": ["$award_date", "$publication_date"]}

SOURCES: tuple[str, ...] = ("vestnik", "crz", "ted", "uvo", "itms")
GRANULARITIES: tuple[str, ...] = ("month", "quarter", "year")
NO_CPV = "00000000"

MAX_SPAN_YEARS = 15
DEFAULT_WINDOW_YEARS = 4  # 1 January of (year - 4): five calendar years incl. the current one
EARLIEST_YEAR = 1993

HHI_LOW_MAX = 1500.0
HHI_MODERATE_MAX = 2500.0

FRESHNESS_WARN_SECONDS = 86_400  # 24 h
FRESHNESS_STALE_SECONDS = 172_800  # 48 h

_CPV_RE = re.compile(r"^\d{2,8}$")
_ICO_RE = re.compile(r"^\d{1,12}$")


class FilterValidationError(ValueError):
    """A dashboard filter value is invalid; ``field`` names the offending parameter."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def _parse_date(field: str, value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise FilterValidationError(field, f"{field} must be an ISO date (YYYY-MM-DD)") from None


def _add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February -> 28 February
        return day.replace(year=day.year + years, day=28)


@dataclass(frozen=True)
class DashboardFilter:
    """Common dashboard filter; hashable so it doubles as the cache key."""

    date_from: str | None = None
    date_to: str | None = None
    cpv: str | None = None
    source: str | None = None
    procurer_ico: str | None = None
    supplier_ico: str | None = None

    def with_defaults(self, today: date) -> DashboardFilter:
        """Fill missing dates: end = today, start = 1 January four years before the end year."""
        date_to = self.date_to or today.isoformat()
        date_from = self.date_from
        if date_from is None:
            try:
                end_year = date.fromisoformat(date_to).year
            except ValueError:
                end_year = today.year  # validate() reports the bad date_to
            date_from = f"{end_year - DEFAULT_WINDOW_YEARS:04d}-01-01"
        return replace(self, date_from=date_from, date_to=date_to)

    def validate(self) -> None:
        """Raise ``FilterValidationError`` for out-of-contract values (callers map it to 422)."""
        if self.date_from is None or self.date_to is None:
            raise FilterValidationError("date_from", "dates must be set; call with_defaults first")
        start = _parse_date("date_from", self.date_from)
        end = _parse_date("date_to", self.date_to)
        if start > end:
            raise FilterValidationError("date_to", "date_from must not be after date_to")
        if end > _add_years(start, MAX_SPAN_YEARS):
            raise FilterValidationError(
                "date_from", f"date range must not exceed {MAX_SPAN_YEARS} years"
            )
        if self.cpv is not None and not _CPV_RE.match(self.cpv):
            raise FilterValidationError("cpv", "cpv must be 2-8 digits")
        if self.source is not None and self.source not in SOURCES:
            raise FilterValidationError("source", f"source must be one of {', '.join(SOURCES)}")
        for name in ("procurer_ico", "supplier_ico"):
            value = getattr(self, name)
            if value is not None and not _ICO_RE.match(value):
                raise FilterValidationError(name, f"{name} must be 1-12 digits")

    def previous_period(self) -> DashboardFilter | None:
        """Same-length window immediately before ``date_from``; None before 1993."""
        start = _parse_date("date_from", self.date_from or "")
        end = _parse_date("date_to", self.date_to or "")
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - (end - start)
        if prev_start.year < EARLIEST_YEAR:
            return None
        return replace(self, date_from=prev_start.isoformat(), date_to=prev_end.isoformat())

    def as_meta(self) -> dict:
        """The ``meta.filters`` echo (all six keys, None when unset)."""
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "cpv": self.cpv,
            "source": self.source,
            "procurer_ico": self.procurer_ico,
            "supplier_ico": self.supplier_ico,
        }


def hhi(values: list[float] | tuple[float, ...]) -> float:
    """Herfindahl-Hirschman index (0-10000) over entity values; non-positive values ignored."""
    positive = [float(v) for v in values if v and v > 0]
    total = sum(positive)
    if total <= 0:
        return 0.0
    return 10_000.0 * sum(v * v for v in positive) / (total * total)


def hhi_band(value: float) -> str:
    """Orientation band: ``low`` < 1500, ``moderate`` up to 2500, else ``high``."""
    if value < HHI_LOW_MAX:
        return "low"
    if value <= HHI_MODERATE_MAX:
        return "moderate"
    return "high"


def period_key(day: str, granularity: str) -> str:
    """Bucket label for an ISO date (or ``YYYY-MM`` / ``YYYY`` prefix)."""
    year = day[:4]
    if granularity == "year":
        return year
    month = int(day[5:7])
    if granularity == "month":
        return f"{year}-{month:02d}"
    if granularity == "quarter":
        return f"{year}-Q{(month - 1) // 3 + 1}"
    raise ValueError(f"unknown granularity {granularity!r}")


def zero_filled_periods(date_from: str, date_to: str, granularity: str) -> list[str]:
    """Every bucket label between two ISO dates, inclusive and ordered."""
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    keys: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        key = period_key(f"{year:04d}-{month:02d}-01", granularity)
        if not keys or keys[-1] != key:
            keys.append(key)
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return keys


def cpv_division(code: str | None) -> str:
    """8-digit CPV division code (first two digits) or ``00000000`` when absent."""
    if not code:
        return NO_CPV
    digits = cpv_prefix(code)[:2]
    return NO_CPV if digits == "00" else f"{digits}000000"


def cpv_group(code: str | None) -> str:
    """8-digit CPV group code (first three digits) or ``00000000`` when absent."""
    if not code:
        return NO_CPV
    digits = cpv_prefix(code)[:3]
    return NO_CPV if digits.startswith("00") else f"{digits}00000"


def freshness_status(age_seconds: float | None, source: str) -> str:
    """healthy <= 24 h, warning <= 48 h, stale beyond; ``legacy`` for uvo, ``unknown`` if empty."""
    if source == "uvo":
        return "legacy"
    if age_seconds is None:
        return "unknown"
    if age_seconds <= FRESHNESS_WARN_SECONDS:
        return "healthy"
    if age_seconds <= FRESHNESS_STALE_SECONDS:
        return "warning"
    return "stale"
