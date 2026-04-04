"""Vestník transformer — map Vestník raw dicts to canonical models."""

import logging
from datetime import date

from slugify import slugify

from uvo_pipeline.models import CanonicalNotice, CanonicalProcurer

logger = logging.getLogger(__name__)

# Map eForms notice type codes to our canonical types
NOTICE_TYPE_MAP = {
    "CN": "contract_notice",        # Contract Notice
    "CAN": "contract_award",        # Contract Award Notice
    "PIN": "prior_information",     # Prior Information Notice
    "CORR": "other",                # Corrigendum
    "CM": "contract_modification",  # Contract Modification
    None: "other",
}


def transform_notice(raw: dict) -> CanonicalNotice:
    """Map Vestník XML raw dict → CanonicalNotice."""
    notice_type = NOTICE_TYPE_MAP.get(raw.get("form_type"), "other")
    status = "awarded" if notice_type == "contract_award" else (
        "announced" if notice_type == "contract_notice" else "unknown"
    )

    procurer = None
    if raw.get("procurer_name"):
        procurer = CanonicalProcurer(
            ico=raw.get("procurer_ico"),
            name=raw["procurer_name"],
            name_slug=slugify(raw["procurer_name"]),
            sources=["vestnik"],
        )

    final_value = None
    if raw.get("total_value"):
        try:
            final_value = float(raw["total_value"])
        except (ValueError, TypeError):
            pass

    estimated_value = None
    if raw.get("estimated_value"):
        try:
            estimated_value = float(raw["estimated_value"])
        except (ValueError, TypeError):
            pass

    pub_date = None
    if raw.get("publication_date"):
        try:
            pub_date = date.fromisoformat(raw["publication_date"][:10])
        except (ValueError, TypeError):
            pass

    title = raw.get("title") or raw.get("notice_id") or "Untitled notice"

    return CanonicalNotice(
        source="vestnik",
        source_id=raw["notice_id"],
        notice_type=notice_type,
        status=status,
        title=title,
        procurer=procurer,
        cpv_code=raw.get("cpv_code"),
        estimated_value=estimated_value,
        final_value=final_value,
        currency=raw.get("currency", "EUR"),
        publication_date=pub_date,
    )
