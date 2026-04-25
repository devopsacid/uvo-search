"""CRZ transformer — map raw CRZ contract dicts to CanonicalNotice.

The Ekosystem CRZ /sync endpoint returns contract objects with English field
names (subject, signed_on, supplier_name, contracting_authority_name,
contract_price_total_amount, etc.). Field names below mirror that schema.
"""

import logging
from datetime import date

from slugify import slugify

from uvo_pipeline.models import (
    CanonicalAttachment,
    CanonicalAward,
    CanonicalNotice,
    CanonicalProcurer,
    CanonicalSupplier,
)

logger = logging.getLogger(__name__)


def _parse_date(value: str | None) -> date | None:
    """Parse a YYYY-MM-DD (optionally with time) string to a date."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        logger.warning("CRZ: could not parse date: %r", value)
        return None


def _parse_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _coerce_ico(raw: dict, prefix: str) -> str | None:
    """CRZ exposes both *_cin (cleaned int) and *_cin_raw (string). Prefer raw."""
    val = raw.get(f"{prefix}_cin_raw")
    if val:
        return str(val)
    val = raw.get(f"{prefix}_cin")
    return str(val) if val is not None else None


def _build_procurer(raw: dict) -> CanonicalProcurer | None:
    name = raw.get("contracting_authority_name") or ""
    if not name:
        return None
    return CanonicalProcurer(
        ico=_coerce_ico(raw, "contracting_authority"),
        name=name,
        name_slug=slugify(name),
        sources=["crz"],
    )


_CRZ_ATTACHMENT_BASE = "https://www.crz.gov.sk/data/att"


def _build_attachments(raw: dict) -> list[CanonicalAttachment]:
    result = []
    for att in raw.get("attachments") or []:
        file_name = att.get("file_name")
        if not file_name:
            continue
        result.append(
            CanonicalAttachment(
                attachment_id=str(att["id"]),
                title=att.get("title"),
                url=f"{_CRZ_ATTACHMENT_BASE}/{file_name}",
                file_name=file_name,
                file_size=att.get("file_size"),
            )
        )
    return result


def _build_awards(raw: dict) -> list[CanonicalAward]:
    name = raw.get("supplier_name") or ""
    if not name:
        return []
    supplier = CanonicalSupplier(
        ico=_coerce_ico(raw, "supplier"),
        name=name,
        name_slug=slugify(name),
        sources=["crz"],
    )
    return [
        CanonicalAward(
            supplier=supplier,
            value=_parse_float(raw.get("contract_price_total_amount")),
            currency="EUR",
            signing_date=_parse_date(raw.get("signed_on")),
        )
    ]


def transform_contract(raw: dict) -> CanonicalNotice:
    """Map a CRZ contract dict (from /sync or /:id) → CanonicalNotice."""
    contract_id = str(raw["id"])

    return CanonicalNotice(
        source="crz",
        source_id=contract_id,
        notice_type="contract_award",
        status="awarded",
        title=raw.get("subject") or raw.get("contract_identifier") or "Unnamed contract",
        description=raw.get("subject_description"),
        procurer=_build_procurer(raw),
        awards=_build_awards(raw),
        final_value=_parse_float(raw.get("contract_price_total_amount")),
        estimated_value=_parse_float(raw.get("contract_price_amount")),
        currency="EUR",
        publication_date=_parse_date(raw.get("signed_on")),
        crz_contract_id=contract_id,
        attachments=_build_attachments(raw),
    )
