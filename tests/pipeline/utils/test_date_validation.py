"""Tests for date_validation utility."""
from datetime import date

import pytest

from uvo_pipeline.models import (
    CanonicalAward,
    CanonicalNotice,
    CanonicalSupplier,
)
from uvo_pipeline.utils.date_validation import (
    MIN_YEAR,
    max_year,
    validate_notice_dates,
)


def _supplier(name="Acme s.r.o."):
    return CanonicalSupplier(name=name, name_slug="acme-sro")


def _make_notice(**overrides) -> CanonicalNotice:
    base = dict(
        source="vestnik",
        source_id="N1",
        notice_type="contract_award",
        title="Test",
    )
    base.update(overrides)
    return CanonicalNotice(**base)


def test_valid_dates_pass_through():
    notice = _make_notice(
        publication_date=date(2025, 1, 1),
        award_date=date(2025, 3, 1),
        deadline_date=date(2026, 1, 1),
    )
    cleaned, issues = validate_notice_dates(notice)
    assert issues == []
    assert cleaned.publication_date == date(2025, 1, 1)
    assert cleaned.award_date == date(2025, 3, 1)
    assert cleaned.deadline_date == date(2026, 1, 1)


def test_year_above_max_is_nulled_and_logged():
    notice = _make_notice(publication_date=date(3202, 1, 15))
    cleaned, issues = validate_notice_dates(notice)
    assert cleaned.publication_date is None
    assert len(issues) == 1
    assert issues[0]["field"] == "publication_date"
    assert issues[0]["year"] == 3202
    assert issues[0]["reason"] == "year_above_max"


def test_year_below_min_is_nulled_and_logged():
    notice = _make_notice(award_date=date(1899, 6, 1))
    cleaned, issues = validate_notice_dates(notice)
    assert cleaned.award_date is None
    assert issues[0]["field"] == "award_date"
    assert issues[0]["year"] == 1899
    assert issues[0]["reason"] == "year_below_min"


def test_signing_date_inside_award_validated():
    notice = _make_notice(
        awards=[
            CanonicalAward(
                supplier=_supplier(),
                signing_date=date(2502, 5, 1),
            )
        ],
    )
    cleaned, issues = validate_notice_dates(notice)
    assert cleaned.awards[0].signing_date is None
    assert any(
        i["field"] == "awards[0].signing_date" and i["year"] == 2502 for i in issues
    )


def test_multiple_bad_dates_all_logged():
    notice = _make_notice(
        publication_date=date(3202, 1, 15),
        award_date=date(2502, 1, 15),
    )
    cleaned, issues = validate_notice_dates(notice)
    assert cleaned.publication_date is None
    assert cleaned.award_date is None
    assert {i["field"] for i in issues} == {"publication_date", "award_date"}


def test_constants_sane():
    assert MIN_YEAR <= 1995
    assert max_year() >= 2030
