"""CRZ transformer — map raw CRZ contract dicts to CanonicalNotice."""

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
        logger.warning("CRZ: could not parse date: %r", value)
        return None


def _build_procurer(objednavatel: dict) -> CanonicalProcurer:
    name = objednavatel.get("nazov") or ""
    return CanonicalProcurer(
        ico=objednavatel.get("ico"),
        name=name,
        name_slug=slugify(name),
        sources=["crz"],
    )


def _build_awards(raw: dict) -> list[CanonicalAward]:
    dodavatel = raw.get("dodavatel", {})
    if not dodavatel:
        return []
    name = dodavatel.get("nazov") or ""
    supplier = CanonicalSupplier(
        ico=dodavatel.get("ico"),
        name=name,
        name_slug=slugify(name),
        sources=["crz"],
    )
    value = raw.get("celkova_hodnota")
    currency = raw.get("mena") or "EUR"
    return [CanonicalAward(supplier=supplier, value=value, currency=currency)]


def transform_contract(raw: dict) -> CanonicalNotice:
    """Map a CRZ contract dict → CanonicalNotice."""
    contract_id = str(raw["id"])

    objednavatel = raw.get("objednavatel", {})
    procurer = _build_procurer(objednavatel) if objednavatel else None

    return CanonicalNotice(
        source="crz",
        source_id=contract_id,
        notice_type="contract_award",
        status="awarded",
        title=raw.get("predmet") or "Unnamed contract",
        procurer=procurer,
        awards=_build_awards(raw),
        final_value=raw.get("celkova_hodnota"),
        currency=raw.get("mena") or "EUR",
        publication_date=_parse_date(raw.get("datum_podpisu")),
        crz_contract_id=contract_id,
    )
