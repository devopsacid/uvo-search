"""Tests for Vestník transformer."""

from datetime import date

from uvo_pipeline.transformers.vestnik import transform_notice

RAW_CAN = {
    "notice_id": "2024/SK-123",
    "form_type": "CAN",
    "procurer_name": "Ministry of Finance",
    "procurer_ico": "12345678",
    "estimated_value": "100000.00",
    "total_value": "95000.00",
    "currency": "EUR",
    "cpv_code": "72000000-5",
    "publication_date": "2024-06-01",
    "title": "IT Software",
}


def test_transform_maps_notice_type():
    result = transform_notice(RAW_CAN)
    assert result.notice_type == "contract_award"
    assert result.status == "awarded"
    assert result.source == "vestnik"
    assert result.source_id == "2024/SK-123"


def test_transform_maps_values():
    result = transform_notice(RAW_CAN)
    assert result.final_value == 95000.0
    assert result.estimated_value == 100000.0
    assert result.currency == "EUR"


def test_transform_maps_procurer():
    result = transform_notice(RAW_CAN)
    assert result.procurer is not None
    assert result.procurer.name == "Ministry of Finance"
    assert result.procurer.ico == "12345678"


def test_transform_cn_notice_type():
    raw = {**RAW_CAN, "form_type": "CN"}
    result = transform_notice(raw)
    assert result.notice_type == "contract_notice"
    assert result.status == "announced"


def test_transform_handles_missing_value():
    raw = {**RAW_CAN, "total_value": None}
    result = transform_notice(raw)
    assert result.final_value is None


def test_transform_handles_no_procurer():
    raw = {**RAW_CAN, "procurer_name": None}
    result = transform_notice(raw)
    assert result.procurer is None
