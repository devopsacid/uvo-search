"""Date plausibility validator for canonical notices.

Source data sometimes contains malformed years (e.g. 3202 from a typo of
2032, or 2502). Pydantic accepts these because Python's `date` allows
year 1..9999. We clamp to a sane window and report each clamp as an
issue so callers can log it to `ingestion_log`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from uvo_pipeline.models import CanonicalNotice

MIN_YEAR = 1995
MAX_YEAR_DELTA = 5  # allow 5 years into the future for tender deadlines


def max_year() -> int:
    return datetime.now(timezone.utc).year + MAX_YEAR_DELTA


def _check(value: date | None, field: str, issues: list[dict[str, Any]]) -> date | None:
    if value is None:
        return None
    year = value.year
    if year < MIN_YEAR:
        issues.append({"field": field, "year": year, "reason": "year_below_min"})
        return None
    if year > max_year():
        issues.append({"field": field, "year": year, "reason": "year_above_max"})
        return None
    return value


def validate_notice_dates(
    notice: CanonicalNotice,
) -> tuple[CanonicalNotice, list[dict[str, Any]]]:
    """Return a copy of `notice` with implausible dates nulled out, plus the issue list.

    Issues are dicts: `{field, year, reason}`. `field` uses dotted paths
    for nested awards (e.g. `awards[0].signing_date`).
    """
    issues: list[dict[str, Any]] = []
    data = notice.model_dump()

    data["publication_date"] = _check(notice.publication_date, "publication_date", issues)
    data["award_date"] = _check(notice.award_date, "award_date", issues)
    data["deadline_date"] = _check(notice.deadline_date, "deadline_date", issues)

    new_awards = []
    for i, award in enumerate(notice.awards):
        adata = award.model_dump()
        adata["signing_date"] = _check(
            award.signing_date, f"awards[{i}].signing_date", issues
        )
        new_awards.append(adata)
    data["awards"] = new_awards

    return CanonicalNotice.model_validate(data), issues
