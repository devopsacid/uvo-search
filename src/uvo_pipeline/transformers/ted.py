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
    CanonicalAward,
    CanonicalNotice,
    CanonicalProcurer,
    CanonicalSupplier,
)

logger = logging.getLogger(__name__)

# TED v3 notice-type values → canonical notice_type / status.
# Full list at https://docs.ted.europa.eu/eforms/latest/codelists/notice-type.html;
# we map the ones relevant to SK procurement here, defaulting to "other"/"unknown".
_CAN_TYPES = {"can-standard", "can-modif", "can-social", "can-desg", "can-tran"}
_CN_TYPES = {"cn-standard", "cn-social", "cn-desg"}


def _map_notice_type(notice_type_value: str) -> tuple[str, str]:
    if notice_type_value in _CAN_TYPES:
        return "contract_award", "awarded"
    if notice_type_value in _CN_TYPES:
        return "contract_notice", "announced"
    return "other", "unknown"

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
        # TED often wraps each language value in a list: {"slk": ["Name"]}
        def _as_str(v: object) -> str | None:
            if isinstance(v, str) and v:
                return v
            if isinstance(v, list) and v:
                first = v[0]
                return first if isinstance(first, str) and first else None
            return None

        for lang in _LANG_PREFERENCE:
            picked = _as_str(value.get(lang))
            if picked:
                return picked
        for v in value.values():
            picked = _as_str(v)
            if picked:
                return picked
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


_SK_ICO_RE = re.compile(r"\d{8}")


def _extract_name_list(value: object) -> list[str]:
    """Extract a list of names from a TED field that may be:
    - list[str]            → as-is
    - dict[lang, list[str]] → the list from the preferred language
    - dict[lang, str]      → [that string]
    - list[dict]           → one _pick_lang per entry
    """
    if value is None:
        return []
    if isinstance(value, list):
        if all(isinstance(x, str) for x in value):
            return [x for x in value if x]
        out = []
        for item in value:
            picked = _pick_lang(item)
            if picked:
                out.append(picked)
        return out
    if isinstance(value, dict):
        for lang in _LANG_PREFERENCE:
            v = value.get(lang)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, str) and x]
            if isinstance(v, str) and v:
                return [v]
        for v in value.values():
            if isinstance(v, list):
                strs = [x for x in v if isinstance(x, str) and x]
                if strs:
                    return strs
            elif isinstance(v, str) and v:
                return [v]
    return []


def _build_awards(raw: dict) -> list[CanonicalAward]:
    """Build CanonicalAward list from TED v3 winner/result fields.

    TED v3 shape (confirmed live): winner-name is a multilingual dict whose
    language values are lists (one per awarded lot), e.g. {"slk": ["A", "B"]}.
    winner-identifier is a flat list of identifiers for the winner(s) — may
    contain ICO + VAT + other schemes for a single winner, so don't index
    it in lock-step with names. Per-lot values live in result-value-lot,
    with tender-value as a notice-level fallback.
    """
    names = _extract_name_list(raw.get("winner-name"))
    # Fallback: some SK notices populate only organisation-name-tenderer
    if not names:
        names = _extract_name_list(raw.get("organisation-name-tenderer"))
    if not names:
        return []

    # Pick the first 8-digit identifier as the Slovak ICO (if any).
    raw_ids = raw.get("winner-identifier") or raw.get("organisation-identifier-tenderer") or []
    ico: str | None = None
    for ident in raw_ids:
        s = str(ident) if ident is not None else ""
        if _SK_ICO_RE.fullmatch(s):
            ico = s
            break

    lot_values: list = raw.get("result-value-lot") or []
    lot_currencies: list = raw.get("result-value-cur-lot") or []
    notice_value = _first_float(raw.get("result-value-notice") or raw.get("tender-value"))
    notice_currency = (
        _first_str(raw.get("result-value-cur-notice") or raw.get("tender-value-cur")) or "EUR"
    )

    awards: list[CanonicalAward] = []
    for i, name in enumerate(names):
        value_raw = lot_values[i] if i < len(lot_values) else None
        value = _first_float(value_raw) if value_raw is not None else notice_value

        currency_raw = lot_currencies[i] if i < len(lot_currencies) else None
        currency = (
            _first_str(currency_raw) if currency_raw is not None else notice_currency
        ) or "EUR"

        awards.append(
            CanonicalAward(
                supplier=CanonicalSupplier(
                    name=name,
                    ico=ico,
                    name_slug=slugify(name),
                    sources=["ted"],
                ),
                value=value,
                currency=currency,
            )
        )

    return awards


def transform_ted_notice(raw: dict) -> CanonicalNotice:
    """Map a raw TED API v3 notice dict → CanonicalNotice."""
    nd = str(raw.get("publication-number", ""))
    notice_type, status = _map_notice_type(_first_str(raw.get("notice-type")) or "")

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
        awards=_build_awards(raw),
        final_value=final_value,
        currency=currency,
        cpv_code=cpv_code,
        publication_date=_parse_ted_date(pub_date_str),
        ted_notice_id=ted_id,
    )
