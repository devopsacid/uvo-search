"""Tests for PipelineSettings config."""

from uvo_pipeline.config import PipelineSettings


def test_itms_base_url_default():
    settings = PipelineSettings()
    assert settings.itms_base_url == "https://opendata.itms2014.sk"


def test_itms_rate_limit_default():
    settings = PipelineSettings()
    assert settings.itms_rate_limit == 5.0
