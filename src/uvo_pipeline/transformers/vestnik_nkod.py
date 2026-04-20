"""Vestník NKOD transformer — map eForms bulletin items to CanonicalNotice."""

import logging
import re
from datetime import date

from slugify import slugify

from uvo_pipeline.models import CanonicalNotice, CanonicalProcurer

logger = logging.getLogger(__name__)

NOTICE_TYPE_MAP = {
    "result": "contract_award",
    "planning": "contract_notice",
    "change": "contract_modification",
}

STATUS_MAP = {
    "contract_award": "awarded",
    "contract_notice": "announced",
    "contract_modification": "unknown",
}

_ID_RE = re.compile(r"\(ID:\s*([^)]+)\)\s*$")


def _flatten_eforms(components: list[dict]) -> dict[str, str]:
    flat: dict[str, str] = {}
    if not isinstance(components, list):
        return flat
    for component in components:
        if not isinstance(component, dict):
            continue
        try:
            key = component.get("key")
            value = component.get("value")
            if key is not None and value is not None:
                flat.setdefault(key, value)
            sub = component.get("components")
            if sub:
                for k, v in _flatten_eforms(sub).items():
                    flat.setdefault(k, v)
        except Exception:
            continue
    return flat


def _lookup(flat: dict[str, str], *codes: str) -> str | None:
    for code in codes:
        v = flat.get(code)
        if v:
            return v
    return None


def _parse_partner(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    m = _ID_RE.search(value)
    if m:
        name = value[: m.start()].strip()
        partner_id = m.group(1).strip()
        return name or None, partner_id
    return value.strip() or None, None


def _parse_order(value: str | None) -> str | None:
    if not value:
        return None
    m = _ID_RE.search(value)
    if m:
        return value[: m.start()].strip() or None
    return value.strip() or None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        logger.warning("vestnik_nkod: bad date: %r", value)
        return None


def _parse_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def transform_notice(raw: dict) -> CanonicalNotice:
    components = raw.get("components", [])
    metadata = next(
        (c for c in components if c.get("key") == "metadataWrapper"), {}
    ).get("components", [])
    tabs = next(
        (c for c in components if c.get("key") == "tabs"), {}
    ).get("components", [])

    flat = {**_flatten_eforms(tabs), **_flatten_eforms(metadata)}

    source_id = str(raw["id"])
    ted_notice_id = _lookup(flat, "BT-04-notice")
    notice_type = NOTICE_TYPE_MAP.get(_lookup(flat, "BT-03-notice"), "other")
    status = STATUS_MAP.get(notice_type, "unknown")

    order_name = _parse_order(_lookup(flat, "DL-Metadata-Order"))
    title = order_name or raw.get("name") or "Untitled notice"

    partner_name, _partner_id = _parse_partner(_lookup(flat, "DL-Metadata-Partner"))
    procurer = None
    if partner_name:
        # Vestník is UVO's official gazette; mark procurer provenance as both
        # so cross-source dedup links vestnik notices to any legacy UVO data.
        procurer = CanonicalProcurer(
            name=partner_name,
            name_slug=slugify(partner_name),
            ico=None,
            organisation_type=None,
            sources=["vestnik", "uvo"],
        )

    publication_date = _parse_date(raw.get("_bulletin_publish_date"))

    year = raw.get("_bulletin_year")
    number = raw.get("_bulletin_number")
    vestnik_number = f"{number}/{year}" if year is not None and number is not None else None

    cpv_code = _lookup(flat, "BT-262-Lot")
    final_value = _parse_float(_lookup(flat, "BT-720-Tender"))
    estimated_value = _parse_float(_lookup(flat, "BT-27-Lot", "BT-27-Procedure"))
    currency = _lookup(flat, "BT-720-Tender-Currency", "BT-27-Lot-Currency") or "EUR"

    return CanonicalNotice(
        source="vestnik",
        source_id=source_id,
        notice_type=notice_type,
        status=status,
        title=title,
        procurer=procurer,
        cpv_code=cpv_code,
        estimated_value=estimated_value,
        final_value=final_value,
        currency=currency,
        publication_date=publication_date,
        vestnik_number=vestnik_number,
        ted_notice_id=ted_notice_id,
    )
