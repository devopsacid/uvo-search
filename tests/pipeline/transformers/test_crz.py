"""Tests for the CRZ transformer."""

from datetime import date

from uvo_pipeline.transformers.crz import transform_contract

RAW = {
    "id": "crz-999",
    "predmet": "Road maintenance",
    "objednavatel": {"nazov": "City Hall", "ico": "12345678"},
    "dodavatel": {"nazov": "Roads Inc", "ico": "87654321"},
    "datum_podpisu": "2024-03-01",
    "celkova_hodnota": 80000.0,
    "mena": "EUR",
    "attachments": [
        {"id": 1001, "title": "Zmluva", "file_name": "1001.pdf", "file_size": 102400},
        {"id": 1002, "title": "Príloha č. 1", "file_name": "1002.pdf", "file_size": 51200},
    ],
}


def test_transform_maps_fields():
    r = transform_contract(RAW)
    assert r.source == "crz"
    assert r.source_id == "crz-999"
    assert r.title == "Road maintenance"
    assert r.notice_type == "contract_award"
    assert r.crz_contract_id == "crz-999"


def test_transform_maps_value():
    r = transform_contract(RAW)
    assert r.final_value == 80000.0
    assert r.currency == "EUR"


def test_transform_maps_procurer():
    r = transform_contract(RAW)
    assert r.procurer is not None
    assert r.procurer.ico == "12345678"
    assert r.procurer.name == "City Hall"


def test_transform_maps_supplier():
    r = transform_contract(RAW)
    assert len(r.awards) == 1
    assert r.awards[0].supplier.ico == "87654321"
    assert r.awards[0].value == 80000.0


def test_transform_maps_date():
    r = transform_contract(RAW)
    assert r.publication_date == date(2024, 3, 1)


def test_transform_status_is_awarded():
    r = transform_contract(RAW)
    assert r.status == "awarded"


def test_transform_missing_predmet_uses_fallback():
    raw = {**RAW, "predmet": None}
    r = transform_contract(raw)
    assert r.title == "Unnamed contract"


def test_transform_missing_dodavatel_gives_empty_awards():
    raw = {k: v for k, v in RAW.items() if k != "dodavatel"}
    r = transform_contract(raw)
    assert r.awards == []


def test_transform_missing_objednavatel_gives_none_procurer():
    raw = {k: v for k, v in RAW.items() if k != "objednavatel"}
    r = transform_contract(raw)
    assert r.procurer is None


def test_transform_missing_date_gives_none():
    raw = {**RAW, "datum_podpisu": None}
    r = transform_contract(raw)
    assert r.publication_date is None


def test_transform_integer_id():
    raw = {**RAW, "id": 42}
    r = transform_contract(raw)
    assert r.source_id == "42"
    assert r.crz_contract_id == "42"


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
