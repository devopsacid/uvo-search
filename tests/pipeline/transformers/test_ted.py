"""Tests for the TED transformer (API v3 field names)."""

from datetime import date

from uvo_pipeline.transformers.ted import transform_ted_notice

# v3 field names (kebab-case)
RAW_CAN = {
    "publication-number": "25",
    "publication-date": "20240615",
    "notice-title": "IT services for government",
    "classification-cpv": ["72000000"],
    "buyer-name": "Ministry of Finance",
    "tender-value": 50000.0,
    "tender-value-cur": "EUR",
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
    raw = {**RAW_CAN, "publication-number": "24"}
    r = transform_ted_notice(raw)
    assert r.notice_type == "contract_notice"
    assert r.status == "announced"


def test_transform_handles_missing_title():
    raw = {k: v for k, v in RAW_CAN.items() if k != "notice-title"}
    r = transform_ted_notice(raw)
    assert r.title is not None  # fallback to ted_id


def test_transform_unknown_nd():
    raw = {**RAW_CAN, "publication-number": "99"}
    r = transform_ted_notice(raw)
    assert r.notice_type == "other"
    assert r.status == "unknown"


def test_transform_maps_procurer():
    r = transform_ted_notice(RAW_CAN)
    assert r.procurer is not None
    assert r.procurer.name == "Ministry of Finance"


def test_transform_no_procurer_when_buyer_name_missing():
    raw = {k: v for k, v in RAW_CAN.items() if k != "buyer-name"}
    r = transform_ted_notice(raw)
    assert r.procurer is None


def test_transform_no_cpv_when_classification_missing():
    raw = {k: v for k, v in RAW_CAN.items() if k != "classification-cpv"}
    r = transform_ted_notice(raw)
    assert r.cpv_code is None


def test_transform_source_id_constructed_from_date_and_nd():
    r = transform_ted_notice(RAW_CAN)
    assert r.source_id == "ted-20240615-25"
    assert r.ted_notice_id == "ted-20240615-25"


def test_transform_missing_date_gives_none():
    raw = {k: v for k, v in RAW_CAN.items() if k != "publication-date"}
    r = transform_ted_notice(raw)
    assert r.publication_date is None


def test_transform_awards_empty():
    r = transform_ted_notice(RAW_CAN)
    assert r.awards == []


def test_transform_multilingual_title_prefers_slovak():
    raw = {**RAW_CAN, "notice-title": {"hun": "Szlovákia…", "slk": "IT služby", "eng": "IT services"}}
    r = transform_ted_notice(raw)
    assert r.title == "IT služby"


def test_transform_multilingual_title_falls_back_to_english():
    raw = {**RAW_CAN, "notice-title": {"hun": "Szlovákia…", "eng": "IT services"}}
    r = transform_ted_notice(raw)
    assert r.title == "IT services"


def test_transform_multilingual_title_falls_back_to_any():
    raw = {**RAW_CAN, "notice-title": {"hun": "Szlovákia…"}}
    r = transform_ted_notice(raw)
    assert r.title == "Szlovákia…"


def test_transform_multilingual_buyer_name():
    raw = {**RAW_CAN, "buyer-name": {"slk": "Ministerstvo financií", "eng": "Ministry of Finance"}}
    r = transform_ted_notice(raw)
    assert r.procurer is not None
    assert r.procurer.name == "Ministerstvo financií"


def test_transform_iso_date_with_timezone():
    raw = {**RAW_CAN, "publication-date": "2026-03-13+01:00"}
    r = transform_ted_notice(raw)
    assert r.publication_date == date(2026, 3, 13)


def test_transform_iso_date_plain():
    raw = {**RAW_CAN, "publication-date": "2026-03-13"}
    r = transform_ted_notice(raw)
    assert r.publication_date == date(2026, 3, 13)


def test_transform_tender_value_as_list_of_strings():
    raw = {**RAW_CAN, "tender-value": ["12511.72"], "tender-value-cur": ["EUR"]}
    r = transform_ted_notice(raw)
    assert r.final_value == 12511.72
    assert r.currency == "EUR"


def test_transform_tender_value_as_scalar_string():
    raw = {**RAW_CAN, "tender-value": "999.50"}
    r = transform_ted_notice(raw)
    assert r.final_value == 999.50


def test_transform_publication_date_as_list():
    raw = {**RAW_CAN, "publication-date": ["2026-03-13+01:00"]}
    r = transform_ted_notice(raw)
    assert r.publication_date == date(2026, 3, 13)
