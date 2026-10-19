"""Pure domain helpers behind the analytics dashboards (metric definition D1)."""

from datetime import date

import pytest

from uvo_core.domain.analytics import (
    DashboardFilter,
    FilterValidationError,
    cpv_division,
    cpv_group,
    freshness_status,
    hhi,
    hhi_band,
    period_key,
    zero_filled_periods,
)

TODAY = date(2026, 10, 19)


def test_defaults_start_on_first_january_four_years_back():
    f = DashboardFilter().with_defaults(TODAY)
    assert f.date_from == "2022-01-01"
    assert f.date_to == "2026-10-19"


def test_defaults_keep_explicit_values_and_other_fields():
    f = DashboardFilter(date_from="2023-05-01", cpv="45", source="crz").with_defaults(TODAY)
    assert (f.date_from, f.date_to, f.cpv, f.source) == ("2023-05-01", "2026-10-19", "45", "crz")


def test_default_start_follows_explicit_date_to():
    f = DashboardFilter(date_to="2015-06-30").with_defaults(TODAY)
    assert f.date_from == "2011-01-01"
    f.validate()


def test_filter_is_hashable_cache_key():
    a = DashboardFilter(date_from="2024-01-01", date_to="2024-12-31")
    b = DashboardFilter(date_from="2024-01-01", date_to="2024-12-31")
    assert hash(a) == hash(b) and a == b


def test_previous_period_is_adjacent_and_same_length():
    f = DashboardFilter(date_from="2024-01-01", date_to="2024-12-31")
    prev = f.previous_period()
    assert prev is not None
    assert prev.date_to == "2023-12-31"  # the day before date_from
    assert prev.date_from == "2022-12-31"  # 366 inclusive days, like the 2024 window


def test_previous_period_length_matches_current_in_days():
    f = DashboardFilter(date_from="2024-03-01", date_to="2024-03-31")
    prev = f.previous_period()
    assert prev is not None
    cur_len = (date.fromisoformat(f.date_to) - date.fromisoformat(f.date_from)).days
    prev_len = (date.fromisoformat(prev.date_to) - date.fromisoformat(prev.date_from)).days
    assert cur_len == prev_len
    assert prev.date_to == "2024-02-29"


def test_previous_period_keeps_non_date_filters():
    f = DashboardFilter(date_from="2024-01-01", date_to="2024-01-31", cpv="45", source="crz")
    prev = f.previous_period()
    assert prev is not None and prev.cpv == "45" and prev.source == "crz"


def test_previous_period_is_none_before_1993():
    f = DashboardFilter(date_from="1993-06-01", date_to="2000-01-01")
    assert f.previous_period() is None


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"date_from": "2025-01-01", "date_to": "2024-01-01"}, "date_to"),
        ({"date_from": "2005-01-01", "date_to": "2026-01-01"}, "date_from"),
        ({"date_from": "2024-13-01", "date_to": "2025-01-01"}, "date_from"),
        ({"date_from": "2024-01-01", "date_to": "yesterday"}, "date_to"),
        ({"cpv": "4"}, "cpv"),
        ({"cpv": "450000001"}, "cpv"),
        ({"cpv": "4a"}, "cpv"),
        ({"source": "sap"}, "source"),
        ({"procurer_ico": "abc"}, "procurer_ico"),
        ({"supplier_ico": "1" * 13}, "supplier_ico"),
    ],
)
def test_validate_rejects_bad_input(kwargs, field):
    f = DashboardFilter(**{"date_from": "2024-01-01", "date_to": "2024-12-31", **kwargs})
    with pytest.raises(FilterValidationError) as exc:
        f.validate()
    assert exc.value.field == field
    assert isinstance(exc.value, ValueError)


def test_validate_accepts_fifteen_year_span_and_full_filter():
    DashboardFilter(
        date_from="2011-01-01",
        date_to="2026-01-01",
        cpv="45000000",
        source="vestnik",
        procurer_ico="00151742",
        supplier_ico="35763469",
    ).validate()


def test_as_meta_filters_echoes_all_six_keys():
    f = DashboardFilter(date_from="2024-01-01", date_to="2024-12-31", cpv="45")
    assert f.as_meta() == {
        "date_from": "2024-01-01",
        "date_to": "2024-12-31",
        "cpv": "45",
        "source": None,
        "procurer_ico": None,
        "supplier_ico": None,
    }


def test_hhi_known_values():
    assert hhi([50, 50]) == 5000
    assert hhi([100]) == 10000
    assert hhi([25, 25, 25, 25]) == 2500
    assert hhi([]) == 0.0
    assert hhi([0, 0]) == 0.0
    assert hhi([100, 0, -5]) == 10000  # non-positive entries are ignored


@pytest.mark.parametrize(
    ("value", "band"),
    [(0, "low"), (1499.9, "low"), (1500, "moderate"), (2500, "moderate"), (2500.1, "high")],
)
def test_hhi_band(value, band):
    assert hhi_band(value) == band


@pytest.mark.parametrize(
    ("day", "granularity", "key"),
    [
        ("2024-05-03", "month", "2024-05"),
        ("2024-05-03", "quarter", "2024-Q2"),
        ("2024-01-31", "quarter", "2024-Q1"),
        ("2024-12-01", "quarter", "2024-Q4"),
        ("2024-05-03", "year", "2024"),
        ("2024-05", "quarter", "2024-Q2"),  # month-resolution input is accepted
        ("2024", "year", "2024"),
    ],
)
def test_period_key(day, granularity, key):
    assert period_key(day, granularity) == key


def test_zero_filled_periods_across_year_boundary():
    assert zero_filled_periods("2023-11-15", "2024-02-02", "month") == [
        "2023-11",
        "2023-12",
        "2024-01",
        "2024-02",
    ]
    assert zero_filled_periods("2023-11-15", "2024-04-02", "quarter") == [
        "2023-Q4",
        "2024-Q1",
        "2024-Q2",
    ]
    assert zero_filled_periods("2022-06-01", "2024-02-02", "year") == ["2022", "2023", "2024"]


def test_cpv_division_and_group():
    assert cpv_division("45233120-6") == "45000000"
    assert cpv_division("72000000") == "72000000"
    assert cpv_division(None) == "00000000"
    assert cpv_division("") == "00000000"
    assert cpv_division("00000000") == "00000000"
    assert cpv_group("45233120-6") == "45200000"
    assert cpv_group(None) == "00000000"


@pytest.mark.parametrize(
    ("age", "source", "status"),
    [
        (3600, "vestnik", "healthy"),
        (86400, "vestnik", "healthy"),
        (86401, "vestnik", "warning"),
        (172800, "vestnik", "warning"),
        (172801, "vestnik", "stale"),
        (None, "vestnik", "unknown"),
        (3600, "uvo", "legacy"),
        (None, "uvo", "legacy"),
    ],
)
def test_freshness_status(age, source, status):
    assert freshness_status(age, source) == status
