"""TED transformer — map raw TED notice dicts to CanonicalNotice."""

import logging
from datetime import date
from typing import Literal

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


def _extract_title(raw: dict, fallback: str) -> str:
    """Return the English title or first available language, else fallback."""
    ti = raw.get("TI", {})
    if not isinstance(ti, dict):
        return fallback
    if "EN" in ti:
        return ti["EN"]
    # Try any available language
    for lang_title in ti.values():
        if lang_title:
            return lang_title
    return fallback


def _build_procurer(raw: dict) -> CanonicalProcurer | None:
    ac = raw.get("AC", {})
    if not isinstance(ac, dict):
        return None
    name = ac.get("ON") or ""
    if not name:
        return None
    return CanonicalProcurer(
        name=name,
        name_slug=slugify(name),
        sources=["ted"],
    )


def _build_awards(raw: dict) -> list[CanonicalAward]:
    winners = raw.get("WIN", [])
    if not winners:
        return []

    tv = raw.get("TV", {})
    value = tv.get("VALUE") if isinstance(tv, dict) else None
    currency = (tv.get("CURR") or "EUR") if isinstance(tv, dict) else "EUR"

    awards = []
    for winner in winners:
        if isinstance(winner, dict):
            name = winner.get("ON") or winner.get("NAME") or ""
        else:
            name = str(winner)
        supplier = CanonicalSupplier(
            name=name,
            name_slug=slugify(name),
            sources=["ted"],
        )
        awards.append(CanonicalAward(supplier=supplier, value=value, currency=currency))
    return awards


def transform_ted_notice(raw: dict) -> CanonicalNotice:
    """Map a raw TED notice dict → CanonicalNotice."""
    nd = str(raw.get("ND", ""))
    notice_type = _ND_TO_NOTICE_TYPE.get(nd, "other")
    status = _ND_TO_STATUS.get(nd, "unknown")

    # Prefer ND_OJ as the canonical TED identifier; fall back to constructing one
    ted_id = raw.get("ND_OJ") or f"ted-{raw.get('PD', 'unknown')}-{nd}"
    source_id = ted_id or f"ted-{raw.get('PD', 'unknown')}-{nd}"

    title = _extract_title(raw, fallback=source_id)

    tv = raw.get("TV", {})
    final_value = tv.get("VALUE") if isinstance(tv, dict) else None
    currency = (tv.get("CURR") or "EUR") if isinstance(tv, dict) else "EUR"

    cpv_codes: list[str] = raw.get("OC", []) or []
    cpv_code = cpv_codes[0] if cpv_codes else None

    return CanonicalNotice(
        source="ted",
        source_id=source_id,
        notice_type=notice_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title=title,
        procurer=_build_procurer(raw),
        awards=_build_awards(raw),
        final_value=final_value,
        currency=currency,
        cpv_code=cpv_code,
        publication_date=_parse_ted_date(raw.get("PD")),
        ted_notice_id=ted_id,
    )
