"""Tests for the uvo source Literal in CanonicalNotice."""
import pytest
from pydantic import ValidationError
from uvo_pipeline.models import CanonicalNotice


def test_source_accepts_uvo():
    notice = CanonicalNotice(
        source="uvo",
        source_id="12345",
        notice_type="contract_notice",
        title="Test",
    )
    assert notice.source == "uvo"


def test_source_rejects_unknown():
    with pytest.raises(ValidationError):
        CanonicalNotice(
            source="unknown_source",
            source_id="1",
            notice_type="other",
            title="x",
        )
