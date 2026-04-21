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
    # Vestník is UVO's official gazette; mark both provenances so
    # cross-source dedup can link to legacy UVO-sourced entities.
    assert r.procurer.sources == ["vestnik", "uvo"]


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


# ---------------------------------------------------------------------------
# Award extraction helpers
# ---------------------------------------------------------------------------

def _org_panel(org_id, name, ico=None, country="SVK"):
    """Build a GR-Organisations_panel component."""
    label_text = f"Zoznam organizácii uvedených v oznámení (GR-Organisations) ({org_id})"
    children = [
        _component("GR-Company", sub=[
            _component("BT-500-Organization-Company", name),
        ]),
    ]
    if ico:
        children[0]["components"].append(
            _component("BT-501-Organization-Company-CIN", ico)
        )
    return {
        "key": "GR-Organisations_panel",
        "lang": {"sk": {"group|name|ND-Organization": label_text}},
        "components": children,
    }


def _tp_panel(tp_id, org_id):
    """Build a GR-TenderingParty_panel component."""
    label_text = f"Zoznam uchádzačov (GR-TenderingParty) ({tp_id})"
    return {
        "key": "GR-TenderingParty_panel",
        "lang": {"sk": {"group|name|ND-TenderingParty": label_text}},
        "components": [_component("OPT-300-Tenderer", org_id)],
    }


def _lot_tender_panel(ten_id, tp_id, value=None, currency="EUR"):
    """Build a GR-LotTender_panel component."""
    label_text = f"Zoznam ponúk (GR-LotTender) ({ten_id})"
    subs = [_component("BT-3201-Tender", tp_id)]
    if value is not None:
        subs.append(_component("BT-720-Tender_value", str(value)))
        subs.append(_component("BT-720-Tender_currency", currency))
    return {
        "key": "GR-LotTender_panel",
        "lang": {"sk": {"group|name|ND-LotTender": label_text}},
        "components": subs,
    }


def _lot_result_panel(res_id, ten_id, selected=True, lot_value=None, lot_currency="EUR"):
    """Build a GR-LotResult_panel component."""
    label_text = f"Zoznam výsledkov častí (GR-LotResult) ({res_id})"
    subs = []
    if selected:
        subs.append(_component("GR-Winner", sub=[
            _component("BT-142-LotResult", "selec-w"),
        ]))
    subs.append(_component("GR-LotResult-1", sub=[
        _component("OPT-320-LotResult", f"['{ten_id}']"),
    ]))
    if lot_value is not None:
        subs.append(_component("GR-LotResult-TenderValue", sub=[
            _component("BT-710-LotResult_currencyWrapper", sub=[
                _component("BT-710-LotResult_value", str(lot_value)),
                _component("BT-710-LotResult_currency", lot_currency),
            ]),
        ]))
    return {
        "key": "GR-LotResult_panel",
        "lang": {"sk": {"group|name|ND-LotResult": label_text}},
        "components": subs,
    }


def _raw_with_awards(org_panels, tp_panels, lot_tender_panels, lot_result_panels):
    """Build a raw notice dict with full award tree embedded in components."""
    metadata = _component("metadataWrapper", sub=[
        _component("BT-04-notice", "test-uuid"),
        _component("BT-03-notice", "result"),
        _component("DL-Metadata-Partner", "Test Procurer (ID: 1)"),
        _component("DL-Metadata-Order", "Test Order (ID: 2)"),
    ])
    award_components = [
        _component("GR-Organisations", sub=org_panels),
        _component("GR-TenderingParty", sub=tp_panels),
        _component("GR-LotTender", sub=lot_tender_panels),
        _component("GR-LotResult", sub=lot_result_panels),
    ]
    return {
        "id": 9000001,
        "name": "Test notice",
        "components": [metadata] + award_components,
        "_bulletin_year": 2026,
        "_bulletin_number": 1,
        "_bulletin_publish_date": "2026-01-01T00:00:00",
    }


# ---------------------------------------------------------------------------
# Award tests
# ---------------------------------------------------------------------------

def test_award_basic_single_lot_single_winner():
    raw = _raw_with_awards(
        org_panels=[_org_panel("ORG-0001", "Dodávateľ s.r.o.", ico="12345678")],
        tp_panels=[_tp_panel("TPA-0001", "ORG-0001")],
        lot_tender_panels=[_lot_tender_panel("TEN-0001", "TPA-0001", value="44 774.70")],
        lot_result_panels=[_lot_result_panel("RES-0001", "TEN-0001", selected=True)],
    )
    r = transform_notice(raw)
    assert len(r.awards) == 1
    a = r.awards[0]
    assert a.supplier.name == "Dodávateľ s.r.o."
    assert a.supplier.ico == "12345678"
    assert a.value == pytest.approx(44774.70)
    assert a.currency == "EUR"
    assert a.supplier.sources == ["vestnik", "uvo"]


def test_award_multi_lot():
    raw = _raw_with_awards(
        org_panels=[
            _org_panel("ORG-0001", "Firma A s.r.o.", ico="11111111"),
            _org_panel("ORG-0002", "Firma B a.s.", ico="22222222"),
        ],
        tp_panels=[
            _tp_panel("TPA-0001", "ORG-0001"),
            _tp_panel("TPA-0002", "ORG-0002"),
        ],
        lot_tender_panels=[
            _lot_tender_panel("TEN-0001", "TPA-0001", value="10000.00"),
            _lot_tender_panel("TEN-0002", "TPA-0002", value="20000.00"),
        ],
        lot_result_panels=[
            _lot_result_panel("RES-0001", "TEN-0001", selected=True),
            _lot_result_panel("RES-0002", "TEN-0002", selected=True),
        ],
    )
    r = transform_notice(raw)
    assert len(r.awards) == 2
    names = {a.supplier.name for a in r.awards}
    assert names == {"Firma A s.r.o.", "Firma B a.s."}


def test_award_ico_valid_8digit():
    raw = _raw_with_awards(
        org_panels=[_org_panel("ORG-0001", "Firma", ico="87654321")],
        tp_panels=[_tp_panel("TPA-0001", "ORG-0001")],
        lot_tender_panels=[_lot_tender_panel("TEN-0001", "TPA-0001", value="1000")],
        lot_result_panels=[_lot_result_panel("RES-0001", "TEN-0001")],
    )
    r = transform_notice(raw)
    assert r.awards[0].supplier.ico == "87654321"


def test_award_ico_non_8digit_rejected():
    """TIN (10-digit) must not be accepted as ICO."""
    raw = _raw_with_awards(
        org_panels=[_org_panel("ORG-0001", "Firma", ico="2021511008")],  # 10-digit DIC
        tp_panels=[_tp_panel("TPA-0001", "ORG-0001")],
        lot_tender_panels=[_lot_tender_panel("TEN-0001", "TPA-0001", value="1000")],
        lot_result_panels=[_lot_result_panel("RES-0001", "TEN-0001")],
    )
    r = transform_notice(raw)
    assert r.awards[0].supplier.ico is None


def test_award_fallback_to_bt710_when_no_bt720():
    """When BT-720 tender value is absent, use BT-710 lot result value."""
    raw = _raw_with_awards(
        org_panels=[_org_panel("ORG-0001", "Firma")],
        tp_panels=[_tp_panel("TPA-0001", "ORG-0001")],
        # No value in tender panel
        lot_tender_panels=[_lot_tender_panel("TEN-0001", "TPA-0001")],
        lot_result_panels=[_lot_result_panel("RES-0001", "TEN-0001", lot_value="99\xa0999.99", lot_currency="EUR")],
    )
    r = transform_notice(raw)
    assert len(r.awards) == 1
    assert r.awards[0].value == pytest.approx(99999.99)


def test_award_lot_result_without_selec_w_yields_no_award():
    """LotResult with BT-142 != selec-w must be skipped."""
    raw = _raw_with_awards(
        org_panels=[_org_panel("ORG-0001", "Firma")],
        tp_panels=[_tp_panel("TPA-0001", "ORG-0001")],
        lot_tender_panels=[_lot_tender_panel("TEN-0001", "TPA-0001", value="5000")],
        lot_result_panels=[_lot_result_panel("RES-0001", "TEN-0001", selected=False)],
    )
    r = transform_notice(raw)
    assert r.awards == []
