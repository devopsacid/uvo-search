"""Smoke test for the orchestrator dry_run path."""

import pytest
from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.models import PipelineReport
from uvo_pipeline.orchestrator import run


@pytest.mark.asyncio
async def test_dry_run_returns_valid_pipeline_report():
    settings = PipelineSettings()
    report = await run("recent", settings=settings, dry_run=True)
    assert isinstance(report, PipelineReport)
    assert report.run_id
    assert report.finished_at is not None
    assert report.mode == "recent"
