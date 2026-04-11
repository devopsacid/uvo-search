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


def _derive_notice_type(status: str | None) -> str:
    """Infer notice type from status when no explicit type field is available."""
    if status in ("awarded",):
        return "contract_award"
    if status in ("cancelled",):
        return "cancellation"
    return "contract_notice"


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
    status = _map_status(raw.get("status"))
    title = raw.get("title") or "Unnamed notice"
    return CanonicalNotice(
        source="uvo",
        source_id=str(raw["id"]),
        notice_type=_derive_notice_type(status),  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title=title,
        title_slug=slugify(title),
        procurer=_build_procurer(raw),
        awards=_build_awards(raw),
        cpv_code=raw.get("cpv"),
        estimated_value=raw.get("estimated_value"),
        final_value=raw.get("final_value"),
        currency=raw.get("currency") or "EUR",
        publication_date=_parse_date(raw.get("published_date")),
        award_date=_parse_date(raw.get("award_date")),
    )
