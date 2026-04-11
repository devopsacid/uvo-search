"""UVO transformer — map raw UVO HTML-scraped dicts to CanonicalNotice."""

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

_STATUS_MAP: dict[str, str] = {
    "ukončené": "awarded",
    "zmluvne ukončené": "awarded",
    "zrušené": "cancelled",
    "prebiehajúce": "announced",
    "vyhlásené": "announced",
}

_NOTICE_TYPE_MAP: dict[str, str] = {
    "zákazka": "contract_notice",
    "verejná zákazka": "contract_notice",
    "zmluva": "contract_award",
    "výsledok": "contract_award",
    "predbežné oznámenie": "prior_information",
}


def _parse_date(value: str | None) -> date | None:
    """Parse an ISO date string 'YYYY-MM-DD' to a date, returning None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        logger.warning("UVO: could not parse date: %r", value)
        return None


def _map_status(raw_status: str | None) -> str:
    if not raw_status:
        return "unknown"
    return _STATUS_MAP.get(raw_status.strip().lower(), "unknown")


def _map_notice_type(raw_type: str | None) -> str:
    if not raw_type:
        return "other"
    return _NOTICE_TYPE_MAP.get(raw_type.strip().lower(), "other")


def _build_procurer(raw: dict) -> CanonicalProcurer | None:
    name = raw.get("procurer_name")
    if not name:
        return None
    return CanonicalProcurer(
        ico=raw.get("procurer_ico"),
        name=name,
        name_slug=slugify(name),
        sources=["uvo"],
    )


def _build_awards(raw: dict) -> list[CanonicalAward]:
    supplier_name = raw.get("supplier_name")
    if not supplier_name:
        return []
    supplier = CanonicalSupplier(
        ico=raw.get("supplier_ico"),
        name=supplier_name,
        name_slug=slugify(supplier_name),
        sources=["uvo"],
    )
    return [
        CanonicalAward(
            supplier=supplier,
            value=raw.get("final_value"),
            currency=raw.get("currency") or "EUR",
            signing_date=_parse_date(raw.get("award_date")),
        )
    ]


def transform_notice(raw: dict) -> CanonicalNotice:
    """Map a raw UVO dict → CanonicalNotice."""
    return CanonicalNotice(
        source="uvo",
        source_id=str(raw["id"]),
        notice_type=_map_notice_type(raw.get("notice_type_raw")),  # type: ignore[arg-type]
        status=_map_status(raw.get("status")),  # type: ignore[arg-type]
        title=raw.get("title") or "Unnamed notice",
        procurer=_build_procurer(raw),
        awards=_build_awards(raw),
        cpv_code=raw.get("cpv"),
        estimated_value=raw.get("estimated_value"),
        final_value=raw.get("final_value"),
        currency=raw.get("currency") or "EUR",
        publication_date=_parse_date(raw.get("published_date")),
        award_date=_parse_date(raw.get("award_date")),
    )
