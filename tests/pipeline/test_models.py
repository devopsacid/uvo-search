"""Tests for CanonicalNotice model source literal."""

import pytest
from pydantic import ValidationError
from uvo_pipeline.models import CanonicalNotice


def test_source_itms_accepted():
    notice = CanonicalNotice(
        source="itms",
        source_id="123",
        notice_type="contract_notice",
        title="Test",
    )
    assert notice.source == "itms"


def test_source_invalid_rejected():
    with pytest.raises(ValidationError):
        CanonicalNotice(
            source="unknown_source",
            source_id="123",
            notice_type="contract_notice",
            title="Test",
        )
