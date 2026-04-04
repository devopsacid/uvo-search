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
