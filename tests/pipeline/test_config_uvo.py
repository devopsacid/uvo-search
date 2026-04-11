"""Tests for UVO config fields."""
from uvo_pipeline.config import PipelineSettings


def test_uvo_defaults():
    s = PipelineSettings()
    assert s.uvo_base_url == "https://www.uvo.gov.sk"
    assert s.uvo_rate_limit == 1.0
    assert s.uvo_request_delay == 0.5
    assert s.uvo_fetch_details is True


def test_uvo_env_override(monkeypatch):
    monkeypatch.setenv("UVO_BASE_URL", "https://test.uvo.gov.sk")
    monkeypatch.setenv("UVO_RATE_LIMIT", "2.5")
    monkeypatch.setenv("UVO_REQUEST_DELAY", "0.1")
    monkeypatch.setenv("UVO_FETCH_DETAILS", "false")
    s = PipelineSettings()
    assert s.uvo_base_url == "https://test.uvo.gov.sk"
    assert s.uvo_rate_limit == 2.5
    assert s.uvo_request_delay == 0.1
    assert s.uvo_fetch_details is False
