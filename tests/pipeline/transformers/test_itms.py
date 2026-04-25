"""Tests for the ITMS2014+ transformer."""

from datetime import date

from uvo_pipeline.transformers.itms import transform_procurement

PROCUREMENT_1 = {
    "id": 36674224,
    "kod": "VO36674224",
    "nazov": "Dodávka kancelárskeho materiálu",
    "predpokladanaHodnotaZakazky": 15000.0,
    "stav": "Ukoncene",
    "datumZverejneniaVoVestniku": "2023-06-15T00:00:00",
    "hlavnyPredmetHlavnySlovnik": {"id": 101, "kod": "30192000-1"},
    "obstaravatelSubjekt": {"id": 5, "nazov": "Ministerstvo financií SR", "ico": "00151742"},
}
# Real ITMS contract shape (confirmed by API probe)
CONTRACT_1 = {
    "id": 1001,
    "hlavnyDodavatelDodavatelObstaravatel": {
        "href": "/v2/dodavatelia/200",
        "ico": "12345678",
        "id": 200,
    },
    "celkovaSumaZmluvy": 14500.0,
    "_supplier": {"id": 200, "nazov": "Office supplies s.r.o.", "ico": "12345678"},
}


def _raw(**overrides):
    """Build a raw procurement dict with optional field overrides."""
    base = dict(PROCUREMENT_1)
    base["_contracts"] = [CONTRACT_1]
    base.update(overrides)
    return base


def test_transform_source_and_source_id():
    r = transform_procurement(_raw())
    assert r.source == "itms"
    assert r.source_id == str(PROCUREMENT_1["id"])


def test_transform_title():
    r = transform_procurement(_raw())
    assert r.title == "Dodávka kancelárskeho materiálu"


def test_transform_title_fallback_when_missing():
    r = transform_procurement(_raw(nazov=None))
    assert r.title == "Unnamed procurement"


def test_transform_notice_type_contract_award_when_ukoncene_with_contracts():
    r = transform_procurement(_raw(stav="Ukoncene"))
    assert r.notice_type == "contract_award"


def test_transform_notice_type_contract_notice_when_active():
    r = transform_procurement(_raw(stav="Prebieha", _contracts=[]))
    assert r.notice_type == "contract_notice"


def test_transform_notice_type_contract_notice_when_ukoncene_no_contracts():
    r = transform_procurement(_raw(stav="Ukoncene", _contracts=[]))
    assert r.notice_type == "contract_notice"


def test_transform_status_awarded():
    r = transform_procurement(_raw(stav="Ukoncene"))
    assert r.status == "awarded"


def test_transform_status_announced_for_prebieha():
    r = transform_procurement(_raw(stav="Prebieha"))
    assert r.status == "announced"


def test_transform_status_cancelled():
    r = transform_procurement(_raw(stav="Zrusene"))
    assert r.status == "cancelled"


def test_transform_status_unknown_for_unrecognised_stav():
    r = transform_procurement(_raw(stav="SomethingElse"))
    assert r.status == "unknown"


def test_transform_publication_date():
    r = transform_procurement(_raw())
    assert r.publication_date == date(2023, 6, 15)


def test_transform_publication_date_none_when_missing():
    r = transform_procurement(_raw(datumZverejneniaVoVestniku=None))
    assert r.publication_date is None


def test_transform_cpv_code():
    r = transform_procurement(_raw())
    assert r.cpv_code == "30192000-1"


def test_transform_cpv_code_none_when_missing():
    r = transform_procurement(_raw(hlavnyPredmetHlavnySlovnik=None))
    assert r.cpv_code is None


def test_transform_estimated_value():
    r = transform_procurement(_raw())
    assert r.estimated_value == 15000.0


def test_transform_procurer_name_and_ico():
    r = transform_procurement(_raw())
    assert r.procurer is not None
    assert r.procurer.name == "Ministerstvo financií SR"
    assert r.procurer.ico == "00151742"


def test_transform_procurer_none_when_missing():
    r = transform_procurement(_raw(obstaravatelSubjekt=None))
    assert r.procurer is None


def test_transform_awards_from_contracts():
    r = transform_procurement(_raw())
    assert len(r.awards) == 1
    award = r.awards[0]
    assert award.supplier.name == "Office supplies s.r.o."
    assert award.supplier.ico == "12345678"
    assert award.value == 14500.0
    assert award.currency == "EUR"


def test_transform_awards_empty_when_no_contracts():
    r = transform_procurement(_raw(_contracts=[]))
    assert r.awards == []


def test_transform_award_currency_always_eur():
    """ITMS has no currency field — EUR is hard-coded by policy."""
    contract = {
        "id": 1002,
        "hlavnyDodavatelDodavatelObstaravatel": {"ico": "99999999", "id": 201},
        "celkovaSumaZmluvy": 5000.0,
        "_supplier": {"id": 201, "nazov": "Test s.r.o.", "ico": "99999999"},
    }
    r = transform_procurement(_raw(_contracts=[contract]))
    assert r.awards[0].currency == "EUR"


def test_transform_award_ico_only_when_no_supplier_enrichment():
    """Contract with only inline ICO ref (no _supplier) still emits an award."""
    contract = {
        "id": 1003,
        "hlavnyDodavatelDodavatelObstaravatel": {"ico": "11111111", "id": 301},
        "celkovaSumaZmluvy": 1000.0,
    }
    r = transform_procurement(_raw(_contracts=[contract]))
    assert len(r.awards) == 1
    assert r.awards[0].supplier.ico == "11111111"
    assert r.awards[0].supplier.name == ""


def test_transform_award_skipped_when_no_supplier_info():
    """Contract with no supplier info at all is skipped."""
    contract = {"id": 1004, "celkovaSumaZmluvy": 500.0}
    r = transform_procurement(_raw(_contracts=[contract]))
    assert r.awards == []


def test_transform_awards_multi_supplier_via_suppliers_list():
    """_suppliers list (detail-endpoint shape) produces one award per supplier."""
    contract = {
        "id": 1005,
        "celkovaSumaZmluvy": 2000.0,
        "_suppliers": [
            {"id": 401, "nazov": "Alpha s.r.o.", "ico": "44444444"},
            {"id": 402, "nazov": "Beta s.r.o.", "ico": "55555555"},
        ],
    }
    r = transform_procurement(_raw(_contracts=[contract]))
    assert len(r.awards) == 2
    assert {a.supplier.ico for a in r.awards} == {"44444444", "55555555"}
    assert all(a.value == 2000.0 for a in r.awards)


def test_transform_award_uses_celkova_suma_zmluvy():
    """Value comes from celkovaSumaZmluvy, not the old celkovaHodnotaZmluvy field."""
    contract = {
        "id": 1006,
        "hlavnyDodavatelDodavatelObstaravatel": {"ico": "77777777", "id": 501},
        "celkovaSumaZmluvy": 637287.0,
        "_supplier": {"id": 501, "nazov": "Stavba a.s.", "ico": "77777777"},
    }
    r = transform_procurement(_raw(_contracts=[contract]))
    assert r.awards[0].value == 637287.0


# --- New-shape tests: detail endpoint with reference-only obstaravatelSubjekt + _subject enrichment ---


def _raw_new_shape(**overrides):
    """Realistic payload: detail endpoint shape, no inline procurer fields, _subject enrichment."""
    base = {
        "id": 2,
        "kod": "VO66152197",
        "nazov": "Rozšírenie kapacity ČOV Lozorno",
        "predpokladanaHodnotaZakazky": 328405,
        "stav": "Ukončené",
        "datumZverejneniaVoVestniku": "2014-02-25T00:00:00Z",
        "obstaravatelSubjekt": {"subjekt": {"href": "/v2/subjekty/100184", "id": 100184}},
        "zadavatel": {"subjekt": {"id": 100184, "ico": "00304905", "dic": "2020643669"}},
        "_subject": {"id": 100184, "nazov": "Obec Lozorno", "ico": "00304905"},
        "_contracts": [],
    }
    base.update(overrides)
    return base


def test_new_shape_title_comes_from_detail():
    r = transform_procurement(_raw_new_shape())
    assert r.title == "Rozšírenie kapacity ČOV Lozorno"


def test_new_shape_procurer_from_resolved_subject():
    r = transform_procurement(_raw_new_shape())
    assert r.procurer is not None
    assert r.procurer.name == "Obec Lozorno"
    assert r.procurer.ico == "00304905"
    assert r.procurer.name_slug == "obec-lozorno"


def test_new_shape_procurer_falls_back_to_zadavatel_ico_when_subject_missing():
    raw = _raw_new_shape()
    del raw["_subject"]
    r = transform_procurement(raw)
    assert r.procurer is not None
    assert r.procurer.name == ""
    assert r.procurer.ico == "00304905"  # from zadavatel.subjekt


def test_new_shape_procurer_none_when_no_subject_and_no_zadavatel_ico():
    raw = _raw_new_shape()
    del raw["_subject"]
    del raw["zadavatel"]
    del raw["obstaravatelSubjekt"]
    r = transform_procurement(raw)
    assert r.procurer is None


def test_new_shape_ukoncene_accented_status():
    r = transform_procurement(_raw_new_shape(stav="Ukončené"))
    assert r.status == "awarded"


def test_new_shape_publication_date_with_z_suffix():
    r = transform_procurement(_raw_new_shape())
    assert r.publication_date == date(2014, 2, 25)
