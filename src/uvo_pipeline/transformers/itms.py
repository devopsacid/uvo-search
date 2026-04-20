"""ITMS2014+ transformer.

Reads enriched items produced by the ITMS extractor:
  - raw: procurement detail (singular /v2/verejneObstaravania/{id})
  - raw["_contracts"]: list of contracts for this procurement
  - raw["_subject"]: resolved /v2/subjekty/{id} payload (procurer name/ICO/DIC)

Falls back to legacy flat list-endpoint shape when those extras are absent
(used by older tests/fixtures).
"""

import logging
from datetime import date

from slugify import slugify

from uvo_pipeline.models import (
    CanonicalAward,
    CanonicalNotice,
    CanonicalProcurer,
    CanonicalSupplier,
)

logger = logging.getLogger(__name__)

_STAV_TO_STATUS = {
    "Ukoncene": "awarded",
    "Ukončené": "awarded",
    "Zrusene": "cancelled",
    "Zrušené": "cancelled",
    "Prebieha": "announced",
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        logger.warning("ITMS: bad date: %r", value)
        return None


def _build_procurer(raw: dict) -> CanonicalProcurer | None:
    """Build a procurer from the resolved subject, falling back to inline refs."""
    subject = raw.get("_subject") or {}
    name = subject.get("nazov") or ""
    ico = subject.get("ico")

    if not ico:
        # The detail endpoint embeds ico inline under zadavatel.subjekt
        zadavatel = (raw.get("zadavatel") or {}).get("subjekt") or {}
        ico = zadavatel.get("ico")

    if not name and not ico:
        # Legacy flat-shape fallback (older fixtures/tests)
        legacy = raw.get("obstaravatelSubjekt") or {}
        if "nazov" in legacy or "ico" in legacy:
            name = legacy.get("nazov") or ""
            ico = legacy.get("ico")

    if not name and not ico:
        return None

    return CanonicalProcurer(
        ico=ico,
        name=name,
        name_slug=slugify(name)
        if name
        else f"itms-subject-{(raw.get('obstaravatelSubjekt') or {}).get('subjekt', {}).get('id', '')}",
        sources=["itms"],
    )


def _make_award(sup: dict, value: float | None) -> CanonicalAward:
    name = sup.get("nazov") or ""
    return CanonicalAward(
        supplier=CanonicalSupplier(
            ico=sup.get("ico"),
            name=name,
            name_slug=slugify(name),
            sources=["itms"],
        ),
        value=value,
        currency="EUR",  # ITMS contracts have no currency field; EUR by policy
    )


def _build_awards(contracts: list) -> list[CanonicalAward]:
    awards = []
    for c in contracts:
        value = c.get("celkovaSumaZmluvy")  # real field name confirmed by API probe

        # detail-endpoint shape may have dodavatelia[] (multi-supplier); emit one award each
        multi = c.get("_suppliers")
        if multi:
            for sup in multi:
                if sup.get("ico") or sup.get("nazov"):
                    awards.append(_make_award(sup, value))
            continue

        # prefer enriched supplier (has nazov); fall back to inline ref for ICO-only
        sup = c.get("_supplier") or c.get("hlavnyDodavatelDodavatelObstaravatel") or {}
        if not sup.get("ico") and not sup.get("nazov"):
            continue
        awards.append(_make_award(sup, value))
    return awards


def _cpv_code(raw: dict) -> str | None:
    hlavny = raw.get("hlavnyPredmetHlavnySlovnik")
    if not hlavny:
        return None
    # Legacy flat shape carried {"kod": ...}; new detail shape carries only an id reference
    return hlavny.get("kod")


def transform_procurement(raw: dict) -> CanonicalNotice:
    stav = raw.get("stav", "")
    contracts = raw.get("_contracts", [])
    return CanonicalNotice(
        source="itms",
        source_id=str(raw["id"]),
        notice_type="contract_award"
        if stav in ("Ukoncene", "Ukončené") and contracts
        else "contract_notice",
        status=_STAV_TO_STATUS.get(stav, "unknown"),
        title=raw.get("nazov") or "Unnamed procurement",
        cpv_code=_cpv_code(raw),
        estimated_value=raw.get("predpokladanaHodnotaZakazky"),
        procurer=_build_procurer(raw),
        awards=_build_awards(contracts),
        publication_date=_parse_date(raw.get("datumZverejneniaVoVestniku")),
    )
