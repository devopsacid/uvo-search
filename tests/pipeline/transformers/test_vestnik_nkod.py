"""Tests for Vestník NKOD transformer."""

import pytest
from datetime import date

from uvo_pipeline.transformers.vestnik_nkod import transform_notice


def _component(key, value=None, sub=None):
    """Helper to build an eForms component."""
    c = {"key": key}
    if value is not None:
        c["value"] = value
    if sub is not None:
        c["components"] = sub
    return c


def _raw(**overrides):
    """Build a minimal raw notice dict matching eForms structure."""
    metadata = _component("metadataWrapper", sub=[
        _component("BT-04-notice", "9699fa41-aaaa-bbbb-cccc-dddddddddddd"),
        _component("BT-03-notice", "result"),
        _component("DL-Metadata-Partner", "Hlavné mesto SR Bratislava (ID: 39686)"),
        _component("DL-Metadata-Order", "IT HW a podpora (ID: 422123)"),
    ])
    tabs = _component("tabs", sub=[
        _component("BT-262-Lot", "72000000"),
        _component("BT-720-Tender", "123456.78"),
        _component("BT-720-Tender-Currency", "EUR"),
    ])
    base = {
        "id": 1397309,
        "name": "Oznámenie o výsledku verejného obstarávania (D24)",
        "components": [metadata, tabs],
        "_bulletin_year": 2026,
        "_bulletin_number": 76,
        "_bulletin_publish_date": "2026-04-17T01:02:38",
        "_dataset_uri": "https://data.gov.sk/set/vestnik/V-76-2026",
    }
    base.update(overrides)
    return base


def test_transform_source_and_source_id():
    r = transform_notice(_raw())
    assert r.source == "vestnik"
    assert r.source_id == "1397309"


def test_transform_ted_notice_id():
    r = transform_notice(_raw())
    assert r.ted_notice_id == "9699fa41-aaaa-bbbb-cccc-dddddddddddd"


def test_transform_notice_type_result_to_contract_award():
    r = transform_notice(_raw())
    assert r.notice_type == "contract_award"


def test_transform_notice_type_planning_to_contract_notice():
    metadata = _component("metadataWrapper", sub=[
        _component("BT-03-notice", "planning"),
    ])
    raw = _raw(components=[metadata])
    r = transform_notice(raw)
    assert r.notice_type == "contract_notice"


def test_transform_notice_type_change_to_contract_modification():
    metadata = _component("metadataWrapper", sub=[
        _component("BT-03-notice", "change"),
    ])
    raw = _raw(components=[metadata])
    r = transform_notice(raw)
    assert r.notice_type == "contract_modification"


def test_transform_notice_type_unknown_to_other():
    metadata = _component("metadataWrapper", sub=[
        _component("BT-03-notice", "something_unknown"),
    ])
    raw = _raw(components=[metadata])
    r = transform_notice(raw)
    assert r.notice_type == "other"


def test_transform_status_contract_award_to_awarded():
    r = transform_notice(_raw())
    assert r.status == "awarded"


def test_transform_status_contract_notice_to_announced():
    metadata = _component("metadataWrapper", sub=[
        _component("BT-03-notice", "planning"),
    ])
    raw = _raw(components=[metadata])
    r = transform_notice(raw)
    assert r.status == "announced"


def test_transform_status_contract_modification_to_unknown():
    metadata = _component("metadataWrapper", sub=[
        _component("BT-03-notice", "change"),
    ])
    raw = _raw(components=[metadata])
    r = transform_notice(raw)
    assert r.status == "unknown"


def test_transform_title_from_order():
    r = transform_notice(_raw())
    assert r.title == "IT HW a podpora"


def test_transform_title_fallback_to_name():
    metadata = _component("metadataWrapper", sub=[])
    raw = _raw(components=[metadata])
    r = transform_notice(raw)
    assert r.title == "Oznámenie o výsledku verejného obstarávania (D24)"


def test_transform_title_fallback_to_untitled():
    raw = _raw(
        name=None,
        components=[_component("metadataWrapper", sub=[])]
    )
    r = transform_notice(raw)
    assert r.title == "Untitled notice"


def test_transform_procurer_name_without_id_suffix():
    r = transform_notice(_raw())
    assert r.procurer is not None
    assert r.procurer.name == "Hlavné mesto SR Bratislava"


def test_transform_procurer_ico_none():
    r = transform_notice(_raw())
    assert r.procurer is not None
    assert r.procurer.ico is None


def test_transform_procurer_name_slug():
    r = transform_notice(_raw())
    assert r.procurer is not None
    assert r.procurer.name_slug == "hlavne-mesto-sr-bratislava"


def test_transform_procurer_sources():
    r = transform_notice(_raw())
    assert r.procurer is not None
    assert r.procurer.sources == ["vestnik"]


def test_transform_procurer_none_when_missing():
    metadata = _component("metadataWrapper", sub=[])
    raw = _raw(components=[metadata])
    r = transform_notice(raw)
    assert r.procurer is None


def test_transform_publication_date():
    r = transform_notice(_raw())
    assert r.publication_date == date(2026, 4, 17)


def test_transform_vestnik_number():
    r = transform_notice(_raw())
    assert r.vestnik_number == "76/2026"


def test_transform_cpv_code():
    r = transform_notice(_raw())
    assert r.cpv_code == "72000000"


def test_transform_final_value():
    r = transform_notice(_raw())
    assert r.final_value == 123456.78


def test_transform_final_value_currency():
    r = transform_notice(_raw())
    assert r.currency == "EUR"


def test_transform_first_occurrence_of_duplicate_codes():
    """When BT-262-Lot appears twice, first occurrence wins."""
    tabs = _component("tabs", sub=[
        _component("BT-262-Lot", "72000000"),  # first
        _component("BT-262-Lot", "88000000"),  # second — should be ignored
    ])
    raw = _raw(components=[_component("metadataWrapper", sub=[]), tabs])
    r = transform_notice(raw)
    assert r.cpv_code == "72000000"
