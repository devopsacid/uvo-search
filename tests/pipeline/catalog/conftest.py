"""Extractor tests must not really sleep between retries."""

import pytest


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("uvo_pipeline.utils.http_retry._default_sleep", _instant)
