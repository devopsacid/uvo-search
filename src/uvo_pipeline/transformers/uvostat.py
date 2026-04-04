"""UVOstat transformer — map raw API dicts to canonical models."""

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


def _parse_date(value: str | None) -> date | None:
    """Parse a YYYY-MM-DD string to a date, returning None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        logger.warning("Could not parse date: %r", value)
        return None


def _build_procurer(obst: dict) -> CanonicalProcurer:
    name = obst.get("nazov") or ""
    return CanonicalProcurer(
        ico=obst.get("ico"),
        name=name,
        name_slug=slugify(name),
        uvostat_id=str(obst["id"]) if obst.get("id") is not None else None,
        sources=["uvostat"],
    )


def _build_awards(raw: dict) -> list[CanonicalAward]:
    awards = []
    value = raw.get("hodnota_zmluvy")
    currency = raw.get("mena") or "EUR"
    for dod in raw.get("dodavatelia") or []:
        name = dod.get("nazov") or ""
        supplier = CanonicalSupplier(
            ico=dod.get("ico"),
            name=name,
            name_slug=slugify(name),
            uvostat_id=str(dod["id"]) if dod.get("id") is not None else None,
            sources=["uvostat"],
        )
        awards.append(CanonicalAward(supplier=supplier, value=value, currency=currency))
    return awards


def transform_procurement(raw: dict) -> CanonicalNotice:
    """Map UVOstat /api/ukoncene_obstaravania item to CanonicalNotice."""
    obst = raw.get("obstaravatel")
    procurer = _build_procurer(obst) if obst else None

    return CanonicalNotice(
        source="uvostat",
        source_id=str(raw["id"]),
        notice_type="contract_award",
        status="awarded",
        title=raw.get("nazov") or "",
        procurer=procurer,
        awards=_build_awards(raw),
        final_value=raw.get("hodnota_zmluvy"),
        currency=raw.get("mena") or "EUR",
        cpv_code=raw.get("cpv"),
        publication_date=_parse_date(raw.get("datum_zverejnenia")),
    )


def transform_announced(raw: dict) -> CanonicalNotice:
    """Map /api/vyhlasene_obstaravania item to CanonicalNotice."""
    obst = raw.get("obstaravatel")
    procurer = _build_procurer(obst) if obst else None

    return CanonicalNotice(
        source="uvostat",
        source_id=str(raw["id"]),
        notice_type="contract_notice",
        status="announced",
        title=raw.get("nazov") or "",
        procurer=procurer,
        awards=_build_awards(raw),
        final_value=raw.get("hodnota_zmluvy"),
        currency=raw.get("mena") or "EUR",
        cpv_code=raw.get("cpv"),
        publication_date=_parse_date(raw.get("datum_zverejnenia")),
    )
