"""Stable content hash for CanonicalNotice deduplication."""

import hashlib

from uvo_pipeline.models import CanonicalNotice


def compute_notice_hash(notice: CanonicalNotice) -> str:
    """Return a stable SHA-256 fingerprint of the notice's key fields.

    Only fields that indicate a meaningful content change are included.
    Metadata fields (ingested_at, pipeline_run_id, canonical_id) are excluded.
    """
    award_key = "|".join(
        f"{a.supplier.ico or a.supplier.name_slug}:{a.value or ''}" for a in notice.awards
    )
    parts = [
        notice.source,
        notice.source_id,
        notice.title or "",
        notice.procurer.ico if notice.procurer and notice.procurer.ico else "",
        notice.cpv_code or "",
        str(notice.publication_date) if notice.publication_date else "",
        str(notice.estimated_value) if notice.estimated_value is not None else "",
        str(notice.final_value) if notice.final_value is not None else "",
        award_key,
    ]
    raw = "|".join(parts).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return f"sha256:{digest}"
