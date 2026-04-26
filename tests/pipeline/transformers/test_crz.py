"""Tests for the CRZ transformer (English field schema from /sync endpoint)."""

from datetime import date

from uvo_pipeline.transformers.crz import transform_contract

RAW = {
    "id": 5587100,
    "contract_identifier": "300410578-5-2021-ZNB",
    "subject": "Road maintenance",
    "subject_description": "Patch repair, line painting, drainage",
    "contracting_authority_name": "City Hall",
    "contracting_authority_cin_raw": "12345678",
    "contracting_authority_cin": 12345678,
    "supplier_name": "Roads Inc",
    "supplier_cin_raw": "87654321",
    "supplier_cin": 87654321,
    "signed_on": "2024-03-01",
    "effective_from": "2024-03-15",
    "contract_price_amount": "75000.0",
    "contract_price_total_amount": "80000.0",
    "published_at": "2024-03-05T11:33:54.000000Z",
    "attachments": [
        {"id": 1001, "title": "Zmluva", "file_name": "1001.pdf", "file_size": 102400},
        {"id": 1002, "title": "Príloha č. 1", "file_name": "1002.pdf", "file_size": 51200},
    ],
}


def test_transform_maps_fields():
    r = transform_contract(RAW)
    assert r.source == "crz"
    assert r.source_id == "5587100"
    assert r.title == "Road maintenance"
    assert r.notice_type == "contract_award"
    assert r.crz_contract_id == "5587100"
    assert r.description == "Patch repair, line painting, drainage"


def test_transform_maps_value():
    r = transform_contract(RAW)
    assert r.final_value == 80000.0
    assert r.estimated_value == 75000.0
    assert r.currency == "EUR"


def test_transform_maps_procurer():
    r = transform_contract(RAW)
    assert r.procurer is not None
    assert r.procurer.ico == "12345678"
    assert r.procurer.name == "City Hall"


def test_transform_procurer_falls_back_to_cin_when_raw_missing():
    raw = {**RAW, "contracting_authority_cin_raw": None}
    r = transform_contract(raw)
    assert r.procurer.ico == "12345678"


def test_transform_maps_supplier():
    r = transform_contract(RAW)
    assert len(r.awards) == 1
    assert r.awards[0].supplier.ico == "87654321"
    assert r.awards[0].value == 80000.0
    assert r.awards[0].signing_date == date(2024, 3, 1)


def test_transform_maps_publication_date_from_signed_on():
    r = transform_contract(RAW)
    assert r.publication_date == date(2024, 3, 1)


def test_transform_status_is_awarded():
    r = transform_contract(RAW)
    assert r.status == "awarded"


def test_transform_missing_subject_falls_back_to_identifier():
    raw = {**RAW, "subject": None}
    r = transform_contract(raw)
    assert r.title == "300410578-5-2021-ZNB"


def test_transform_missing_subject_and_identifier_uses_default():
    raw = {**RAW, "subject": None, "contract_identifier": None}
    r = transform_contract(raw)
    assert r.title == "Unnamed contract"


def test_transform_missing_supplier_gives_empty_awards():
    raw = {**RAW, "supplier_name": None}
    r = transform_contract(raw)
    assert r.awards == []


def test_transform_missing_authority_gives_none_procurer():
    raw = {**RAW, "contracting_authority_name": None}
    r = transform_contract(raw)
    assert r.procurer is None


def test_transform_missing_signed_on_gives_none_date():
    raw = {**RAW, "signed_on": None}
    r = transform_contract(raw)
    assert r.publication_date is None


def test_transform_signed_on_with_iso_timestamp_yields_date():
    raw = {**RAW, "signed_on": "2024-03-01T11:33:54.000000Z"}
    r = transform_contract(raw)
    assert r.publication_date == date(2024, 3, 1)


def test_transform_integer_id():
    raw = {**RAW, "id": 42}
    r = transform_contract(raw)
    assert r.source_id == "42"
    assert r.crz_contract_id == "42"


def test_transform_string_price_parses():
    raw = {**RAW, "contract_price_total_amount": "12345.67"}
    r = transform_contract(raw)
    assert r.final_value == 12345.67


def test_transform_unparseable_price_yields_none():
    raw = {**RAW, "contract_price_total_amount": "abc"}
    r = transform_contract(raw)
    assert r.final_value is None


def test_transform_maps_attachments():
    r = transform_contract(RAW)
    assert len(r.attachments) == 2
    att = r.attachments[0]
    assert att.attachment_id == "1001"
    assert att.title == "Zmluva"
    assert att.url == "https://www.crz.gov.sk/data/att/1001.pdf"
    assert att.file_name == "1001.pdf"
    assert att.file_size == 102400


def test_transform_no_attachments_gives_empty_list():
    raw = {k: v for k, v in RAW.items() if k != "attachments"}
    r = transform_contract(raw)
    assert r.attachments == []


def test_transform_attachment_missing_file_name_skipped():
    raw = {**RAW, "attachments": [{"id": 9, "title": "Bad", "file_name": None, "file_size": 0}]}
    r = transform_contract(raw)
    assert r.attachments == []
