"""TED transformer — map raw TED API v3 notice dicts to CanonicalNotice.

TED API v3 uses kebab-case field names:
  publication-number  — notice type code (24=contract_notice, 25=contract_award)
  publication-date    — YYYYMMDD string
  notice-title        — plain string
  classification-cpv  — list of CPV code strings
  buyer-name          — procurer name string
  tender-value        — numeric value
  tender-value-cur    — ISO 4217 currency string
"""

import logging
import re
from datetime import date

from slugify import slugify

from uvo_pipeline.models import (
    CanonicalNotice,
    CanonicalProcurer,
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

# Preferred language order when TED returns a multilingual dict like {"slk": ..., "eng": ...}
_LANG_PREFERENCE = ("slk", "eng", "ces", "deu", "fra")


def _pick_lang(value: object) -> str | None:
    """Collapse TED multilingual fields (dict or list-of-dict) to a single string.

    TED v3 returns some text fields as {"<lang>": "text", ...}. Pick the best
    available language; fall back to any value. Strings pass through unchanged.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            picked = _pick_lang(item)
            if picked:
                return picked
        return None
    if isinstance(value, dict):
        for lang in _LANG_PREFERENCE:
            v = value.get(lang)
            if isinstance(v, str) and v:
                return v
        for v in value.values():
            if isinstance(v, str) and v:
                return v
    return None


def _first_float(value: object) -> float | None:
    """Coerce TED numeric fields (which may arrive as list[str] for multi-lot notices) to a float."""
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _first_str(value: object) -> str | None:
    """Unwrap TED string fields that may arrive wrapped in a list."""
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, str) else None


def _parse_ted_date(value: str | None) -> date | None:
    """Parse a TED date to a Python date, returning None on failure.

    Accepts either legacy compact form 'YYYYMMDD' or ISO 'YYYY-MM-DD' optionally
    followed by a timezone suffix (e.g. '2026-03-13+01:00').
    """
    if not value:
        return None
    try:
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", value)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if len(value) >= 8 and value[:8].isdigit():
            return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except (ValueError, TypeError):
        pass
    logger.warning("TED: could not parse date: %r", value)
    return None


def transform_ted_notice(raw: dict) -> CanonicalNotice:
    """Map a raw TED API v3 notice dict → CanonicalNotice."""
    nd = str(raw.get("publication-number", ""))
    notice_type = _ND_TO_NOTICE_TYPE.get(nd, "other")
    status = _ND_TO_STATUS.get(nd, "unknown")

    pub_date_str = _first_str(raw.get("publication-date")) or ""
    ted_id = raw.get("ND_OJ") or f"ted-{pub_date_str}-{nd}"
    source_id = ted_id

    title = _pick_lang(raw.get("notice-title")) or source_id

    final_value = _first_float(raw.get("tender-value"))
    currency = _first_str(raw.get("tender-value-cur")) or "EUR"

    cpv_codes: list[str] = raw.get("classification-cpv") or []
    cpv_code = cpv_codes[0] if cpv_codes else None

    buyer_name = _pick_lang(raw.get("buyer-name"))
    if buyer_name:
        procurer: CanonicalProcurer | None = CanonicalProcurer(
            name=buyer_name,
            name_slug=slugify(buyer_name),
            sources=["ted"],
        )
    else:
        procurer = None

    return CanonicalNotice(
        source="ted",
        source_id=source_id,
        notice_type=notice_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title=title,
        procurer=procurer,
        awards=[],  # v3 basic search response has no winner field
        final_value=final_value,
        currency=currency,
        cpv_code=cpv_code,
        publication_date=_parse_ted_date(pub_date_str),
        ted_notice_id=ted_id,
    )
