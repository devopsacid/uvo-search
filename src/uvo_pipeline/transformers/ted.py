"""TED transformer — map raw TED notice dicts to CanonicalNotice."""

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

_ND_TO_NOTICE_TYPE: dict[str, str] = {
    "24": "contract_notice",
    "25": "contract_award",
}
_ND_TO_STATUS: dict[str, str] = {
    "24": "announced",
    "25": "awarded",
}


def _parse_ted_date(value: str | None) -> date | None:
    """Parse a YYYYMMDD string to a date, returning None on failure."""
    if not value:
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except (ValueError, TypeError, IndexError):
        logger.warning("TED: could not parse date: %r", value)
        return None


def transform_ted_notice(raw: dict) -> CanonicalNotice:
    """Map a raw TED v3 notice dict → CanonicalNotice."""
    nd = str(raw.get("publication-number", ""))
    notice_type = _ND_TO_NOTICE_TYPE.get(nd, "other")
    status = _ND_TO_STATUS.get(nd, "unknown")

    # v3: publication-number is used as the source_id basis
    pub_date_str = raw.get("publication-date", "")
    ted_id = f"ted-{pub_date_str}-{nd}"
    source_id = ted_id

    # v3: notice-title is a plain string
    title = raw.get("notice-title") or source_id

    # v3: tender-value / tender-value-cur
    final_value = raw.get("tender-value")
    currency = raw.get("tender-value-cur") or "EUR"

    # v3: classification-cpv is a list
    cpv_codes = raw.get("classification-cpv") or []
    cpv_code = cpv_codes[0] if cpv_codes else None

    # v3: buyer-name is a plain string
    buyer_name = raw.get("buyer-name")
    if buyer_name:
        procurer = CanonicalProcurer(
            name=buyer_name,
            name_slug=slugify(buyer_name),
            sources=["ted"],
        )
    else:
        procurer = None

    # v3: no explicit winner field in basic search results — awards empty for now
    awards: list[CanonicalAward] = []

    return CanonicalNotice(
        source="ted",
        source_id=source_id,
        notice_type=notice_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title=title,
        procurer=procurer,
        awards=awards,
        final_value=final_value,
        currency=currency,
        cpv_code=cpv_code,
        publication_date=_parse_ted_date(pub_date_str),
        ted_notice_id=ted_id,
    )
