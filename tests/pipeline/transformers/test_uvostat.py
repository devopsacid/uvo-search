"""Tests for the UVOstat transformer."""

import pytest
from datetime import date

from uvo_pipeline.transformers.uvostat import transform_announced, transform_procurement

RAW_PROCUREMENT = {
    "id": "999",
    "nazov": "IT Software Procurement",
    "obstaravatel": {"id": "10", "nazov": "Ministry of Finance", "ico": "12345678"},
    "dodavatelia": [{"id": "20", "nazov": "Acme Corp", "ico": "87654321"}],
    "hodnota_zmluvy": 50000.0,
    "mena": "EUR",
    "datum_zverejnenia": "2024-06-01",
    "cpv": "72000000-5",
}


def test_transform_maps_required_fields():
    result = transform_procurement(RAW_PROCUREMENT)
    assert result.source == "uvostat"
    assert result.source_id == "999"
    assert result.title == "IT Software Procurement"
    assert result.notice_type == "contract_award"
    assert result.status == "awarded"


def test_transform_maps_procurer():
    result = transform_procurement(RAW_PROCUREMENT)
    assert result.procurer is not None
    assert result.procurer.ico == "12345678"
    assert result.procurer.name == "Ministry of Finance"
    assert result.procurer.uvostat_id == "10"


def test_transform_maps_awards():
    result = transform_procurement(RAW_PROCUREMENT)
    assert len(result.awards) == 1
    assert result.awards[0].supplier.ico == "87654321"
    assert result.awards[0].value == 50000.0


def test_transform_maps_value_and_cpv():
    result = transform_procurement(RAW_PROCUREMENT)
    assert result.final_value == 50000.0
    assert result.currency == "EUR"
    assert result.cpv_code == "72000000-5"


def test_transform_maps_publication_date():
    result = transform_procurement(RAW_PROCUREMENT)
    assert result.publication_date == date(2024, 6, 1)


def test_transform_handles_missing_cpv():
    raw = {**RAW_PROCUREMENT, "cpv": None}
    result = transform_procurement(raw)
    assert result.cpv_code is None


def test_transform_handles_empty_suppliers():
    raw = {**RAW_PROCUREMENT, "dodavatelia": []}
    result = transform_procurement(raw)
    assert result.awards == []


def test_transform_handles_missing_value():
    raw = {**RAW_PROCUREMENT, "hodnota_zmluvy": None}
    result = transform_procurement(raw)
    assert result.final_value is None


def test_transform_announced_sets_correct_type():
    result = transform_announced(RAW_PROCUREMENT)
    assert result.notice_type == "contract_notice"
    assert result.status == "announced"


def test_transform_handles_missing_procurer():
    raw = {**RAW_PROCUREMENT, "obstaravatel": None}
    result = transform_procurement(raw)
    assert result.procurer is None


def test_transform_handles_invalid_date():
    raw = {**RAW_PROCUREMENT, "datum_zverejnenia": "not-a-date"}
    result = transform_procurement(raw)
    assert result.publication_date is None


def test_transform_procurer_name_slug():
    result = transform_procurement(RAW_PROCUREMENT)
    assert result.procurer is not None
    # slugify("Ministry of Finance") => "ministry-of-finance"
    assert result.procurer.name_slug == "ministry-of-finance"


def test_transform_supplier_name_slug():
    result = transform_procurement(RAW_PROCUREMENT)
    assert result.awards[0].supplier.name_slug == "acme-corp"
