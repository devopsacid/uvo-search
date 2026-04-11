"""Tests for the UVO transformer."""
import pytest
from datetime import date
from uvo_pipeline.transformers.uvo import transform_notice

FULL_RAW = {
    "id": "12345",
    "title": "Stavebné práce na moste",
    "procurer_name": "Ministerstvo vnútra SR",
    "procurer_ico": "00151866",
    "cpv": "45221000-2",
    "published_date": "2024-03-15",
    "status": "Ukončené",
    "estimated_value": 500000.0,
    "detail_url": "/vestnik-a-registre/vestnik/oznamenie/detail/12345?cHash=abc123",
    "supplier_name": "Stavby s.r.o.",
    "supplier_ico": "44556677",
    "final_value": 480000.0,
    "award_date": "2024-06-01",
    "currency": "EUR",
}


def test_transform_maps_required_fields():
    notice = transform_notice(FULL_RAW)
    assert notice.source == "uvo"
    assert notice.source_id == "12345"
    assert notice.title == "Stavebné práce na moste"
    assert notice.publication_date == date(2024, 3, 15)
    assert notice.cpv_code == "45221000-2"
    assert notice.estimated_value == 500000.0
    assert notice.status == "awarded"
    assert notice.notice_type == "contract_award"


def test_transform_maps_procurer():
    notice = transform_notice(FULL_RAW)
    assert notice.procurer is not None
    assert notice.procurer.name == "Ministerstvo vnútra SR"
    assert notice.procurer.ico == "00151866"
    assert notice.procurer.name_slug == "ministerstvo-vnutra-sr"
    assert "uvo" in notice.procurer.sources


def test_transform_maps_supplier_to_award():
    notice = transform_notice(FULL_RAW)
    assert len(notice.awards) == 1
    award = notice.awards[0]
    assert award.supplier.name == "Stavby s.r.o."
    assert award.supplier.ico == "44556677"
    assert award.value == 480000.0
    assert award.currency == "EUR"
    assert award.signing_date == date(2024, 6, 1)


def test_transform_handles_missing_supplier():
    raw = {k: v for k, v in FULL_RAW.items() if k not in ("supplier_name", "supplier_ico", "final_value")}
    notice = transform_notice(raw)
    assert notice.awards == []


def test_transform_missing_value_is_none():
    raw = {k: v for k, v in FULL_RAW.items() if k != "estimated_value"}
    notice = transform_notice(raw)
    assert notice.estimated_value is None


def test_transform_missing_date_is_none():
    raw = {**FULL_RAW, "published_date": None}
    notice = transform_notice(raw)
    assert notice.publication_date is None


@pytest.mark.parametrize("uvo_status,expected", [
    ("Ukončené", "awarded"),
    ("Zmluvne ukončené", "awarded"),
    ("Zrušené", "cancelled"),
    ("Prebiehajúce", "announced"),
    ("Vyhlásené", "announced"),
    ("Neznámy stav", "unknown"),
    (None, "unknown"),
])
def test_transform_status_mapping(uvo_status, expected):
    raw = {**FULL_RAW, "status": uvo_status}
    notice = transform_notice(raw)
    assert notice.status == expected


@pytest.mark.parametrize("uvo_status,expected_type", [
    ("Ukončené", "contract_award"),
    ("Zmluvne ukončené", "contract_award"),
    ("Zrušené", "cancellation"),
    ("Prebiehajúce", "contract_notice"),
    ("Vyhlásené", "contract_notice"),
    ("Neznámy stav", "contract_notice"),
    (None, "contract_notice"),
])
def test_transform_notice_type_mapping(uvo_status, expected_type):
    raw = {**FULL_RAW, "status": uvo_status}
    notice = transform_notice(raw)
    assert notice.notice_type == expected_type


def test_transform_no_procurer_when_name_missing():
    raw = {**FULL_RAW, "procurer_name": None}
    notice = transform_notice(raw)
    assert notice.procurer is None


def test_transform_currency_defaults_to_eur():
    raw = {k: v for k, v in FULL_RAW.items() if k != "currency"}
    notice = transform_notice(raw)
    # Awards currency should default to EUR
    assert notice.awards[0].currency == "EUR"
