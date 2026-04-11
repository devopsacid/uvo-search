"""ITMS2014+ transformer."""
import logging
from datetime import date
from slugify import slugify
from uvo_pipeline.models import CanonicalAward, CanonicalNotice, CanonicalProcurer, CanonicalSupplier

logger = logging.getLogger(__name__)

# CanonicalNotice.status Literal: "announced"|"awarded"|"cancelled"|"unknown"
# "Prebieha" (in-progress) -> "announced" (no "active" in the Literal)
_STAV_TO_STATUS = {"Ukoncene": "awarded", "Zrusene": "cancelled", "Prebieha": "announced"}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        logger.warning("ITMS: bad date: %r", value)
        return None


def _build_procurer(subject: dict) -> CanonicalProcurer:
    name = subject.get("nazov") or ""
    return CanonicalProcurer(ico=subject.get("ico"), name=name, name_slug=slugify(name), sources=["itms"])


def _build_awards(contracts: list) -> list[CanonicalAward]:
    awards = []
    for c in contracts:
        d = c.get("dodavatel")
        if not d:
            continue
        name = d.get("nazov") or ""
        awards.append(CanonicalAward(
            supplier=CanonicalSupplier(ico=d.get("ico"), name=name, name_slug=slugify(name), sources=["itms"]),
            value=c.get("celkovaHodnotaZmluvy"),
            currency=c.get("mena") or "EUR",
        ))
    return awards


def transform_procurement(raw: dict) -> CanonicalNotice:
    stav = raw.get("stav", "")
    contracts = raw.get("_contracts", [])
    hlavny = raw.get("hlavnyPredmetHlavnySlovnik")
    subject = raw.get("obstaravatelSubjekt")
    return CanonicalNotice(
        source="itms",
        source_id=str(raw["id"]),
        notice_type="contract_award" if stav == "Ukoncene" and contracts else "contract_notice",
        status=_STAV_TO_STATUS.get(stav, "unknown"),
        title=raw.get("nazov") or "Unnamed procurement",
        cpv_code=hlavny["kod"] if hlavny else None,
        estimated_value=raw.get("predpokladanaHodnotaZakazky"),
        procurer=_build_procurer(subject) if subject else None,
        awards=_build_awards(contracts),
        publication_date=_parse_date(raw.get("datumZverejneniaVoVestniku")),
    )
