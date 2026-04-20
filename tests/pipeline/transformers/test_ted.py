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


def test_transform_awards_empty_when_no_winner_name():
    # RAW_CAN has no winner-name → awards stays empty
    r = transform_ted_notice(RAW_CAN)
    assert r.awards == []


# --- CAN award extraction ---

# TED v3 returns winner-name as a multilingual dict whose language values
# are lists (one per awarded lot). winner-identifier is a flat list that
# may contain multiple identifier schemes (ICO + VAT) for the same winner.
RAW_CAN_SINGLE = {
    **RAW_CAN,
    "winner-name": {"slk": ["Acme s.r.o."]},
    "winner-identifier": ["12345678", "2022116976"],
    "result-value-lot": ["45000.00"],
    "result-value-cur-lot": ["EUR"],
}

RAW_CAN_MULTI = {
    **RAW_CAN,
    "winner-name": {"slk": ["Acme s.r.o.", "Beta a.s."]},
    "winner-identifier": ["12345678"],
    "result-value-lot": ["20000.00", "25000.00"],
    "result-value-cur-lot": ["EUR", "EUR"],
}


def test_awards_single_winner():
    r = transform_ted_notice(RAW_CAN_SINGLE)
    assert len(r.awards) == 1
    a = r.awards[0]
    assert a.supplier.name == "Acme s.r.o."
    assert a.supplier.name_slug == "acme-s-r-o"
    # First 8-digit identifier wins, VAT 2022116976 is ignored
    assert a.supplier.ico == "12345678"
    assert a.value == 45000.0
    assert a.currency == "EUR"


def test_awards_multi_lot():
    r = transform_ted_notice(RAW_CAN_MULTI)
    assert len(r.awards) == 2
    assert r.awards[0].supplier.name == "Acme s.r.o."
    assert r.awards[0].value == 20000.0
    assert r.awards[1].supplier.name == "Beta a.s."
    assert r.awards[1].value == 25000.0
    # All awards share the winner's single ICO
    assert r.awards[0].supplier.ico == "12345678"
    assert r.awards[1].supplier.ico == "12345678"


def test_awards_non_numeric_identifier_gives_ico_none():
    raw = {
        **RAW_CAN,
        "winner-name": {"eng": ["Foreign Corp"]},
        "winner-identifier": ["DE-XYZ-9999", "ABC123"],
    }
    r = transform_ted_notice(raw)
    assert len(r.awards) == 1
    assert r.awards[0].supplier.ico is None


def test_awards_no_winner_name_returns_empty():
    raw = {**RAW_CAN, "winner-name": {}}
    r = transform_ted_notice(raw)
    assert r.awards == []


def test_awards_fallback_to_tenderer_when_no_winner_name():
    # SK notices sometimes populate only organisation-name-tenderer.
    raw = {
        **RAW_CAN,
        "winner-name": {},
        "organisation-name-tenderer": {"slk": ["Tender Company s.r.o."]},
        "organisation-identifier-tenderer": ["31348238"],
    }
    r = transform_ted_notice(raw)
    assert len(r.awards) == 1
    assert r.awards[0].supplier.name == "Tender Company s.r.o."
    assert r.awards[0].supplier.ico == "31348238"


def test_awards_fallback_to_notice_value_when_no_lot_value():
    raw = {
        **RAW_CAN,
        "winner-name": {"slk": ["Fallback Corp"]},
        "result-value-notice": ["99999.00"],
        "result-value-cur-notice": ["EUR"],
    }
    r = transform_ted_notice(raw)
    assert len(r.awards) == 1
    assert r.awards[0].value == 99999.0


def test_awards_fallback_to_tender_value_when_no_result_value():
    raw = {
        **RAW_CAN,
        "winner-name": {"slk": ["Tender Corp"]},
        # Only tender-value available (not result-value-*)
        "tender-value": ["321393.60"],
        "tender-value-cur": ["EUR"],
    }
    r = transform_ted_notice(raw)
    assert len(r.awards) == 1
    assert r.awards[0].value == 321393.60


def test_awards_prefers_slovak_over_other_languages():
    raw = {
        **RAW_CAN,
        "winner-name": {"eng": ["Acme Ltd"], "slk": ["Acme s.r.o."], "deu": ["Acme GmbH"]},
        "winner-identifier": ["12345678"],
    }
    r = transform_ted_notice(raw)
    assert len(r.awards) == 1
    assert r.awards[0].supplier.name == "Acme s.r.o."


def test_transform_multilingual_title_prefers_slovak():
    raw = {
        **RAW_CAN,
        "notice-title": {"hun": "Szlovákia…", "slk": "IT služby", "eng": "IT services"},
    }
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
