"""Tests for the TED transformer."""

from datetime import date

from uvo_pipeline.transformers.ted import transform_ted_notice

RAW_CAN = {
    "ND": "25",
    "PD": "20240615",
    "TI": {"EN": "IT services for government"},
    "OC": ["72000000"],
    "AC": {"ON": "Ministry of Finance"},
    "TV": {"VALUE": 50000.0, "CURR": "EUR"},
}


def test_transform_maps_notice_type():
    r = transform_ted_notice(RAW_CAN)
    assert r.source == "ted"
    assert r.notice_type == "contract_award"
    assert r.status == "awarded"


def test_transform_maps_title():
    r = transform_ted_notice(RAW_CAN)
    assert r.title == "IT services for government"


def test_transform_maps_value():
    r = transform_ted_notice(RAW_CAN)
    assert r.final_value == 50000.0
    assert r.currency == "EUR"


def test_transform_maps_date():
    r = transform_ted_notice(RAW_CAN)
    assert r.publication_date == date(2024, 6, 15)


def test_transform_maps_cpv():
    r = transform_ted_notice(RAW_CAN)
    assert r.cpv_code == "72000000"


def test_transform_cn_notice():
    raw = {**RAW_CAN, "ND": "24"}
    r = transform_ted_notice(raw)
    assert r.notice_type == "contract_notice"
    assert r.status == "announced"


def test_transform_handles_missing_title():
    raw = {**RAW_CAN, "TI": {}}
    r = transform_ted_notice(raw)
    assert r.title is not None  # fallback to source_id


def test_transform_unknown_nd():
    raw = {**RAW_CAN, "ND": "99"}
    r = transform_ted_notice(raw)
    assert r.notice_type == "other"
    assert r.status == "unknown"


def test_transform_maps_procurer():
    r = transform_ted_notice(RAW_CAN)
    assert r.procurer is not None
    assert r.procurer.name == "Ministry of Finance"


def test_transform_no_procurer_when_ac_missing():
    raw = {k: v for k, v in RAW_CAN.items() if k != "AC"}
    r = transform_ted_notice(raw)
    assert r.procurer is None


def test_transform_no_cpv_when_oc_missing():
    raw = {k: v for k, v in RAW_CAN.items() if k != "OC"}
    r = transform_ted_notice(raw)
    assert r.cpv_code is None


def test_transform_nd_oj_used_as_source_id():
    raw = {**RAW_CAN, "ND_OJ": "2024/S 123-456789"}
    r = transform_ted_notice(raw)
    assert r.source_id == "2024/S 123-456789"
    assert r.ted_notice_id == "2024/S 123-456789"


def test_transform_missing_date_gives_none():
    raw = {k: v for k, v in RAW_CAN.items() if k != "PD"}
    r = transform_ted_notice(raw)
    assert r.publication_date is None


def test_transform_fallback_title_from_other_language():
    raw = {**RAW_CAN, "TI": {"SK": "IT služby"}}
    r = transform_ted_notice(raw)
    assert r.title == "IT služby"
