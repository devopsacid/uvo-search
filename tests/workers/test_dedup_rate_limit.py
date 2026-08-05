"""Dedup must not re-run on every batch — it is an O(n^2) scan."""

from uvo_workers import dedup


def test_minimum_interval_is_at_least_60_seconds():
    assert dedup.MIN_DEDUP_INTERVAL_SECONDS >= 60, (
        "dedup performs a full-collection quadratic scan; running it every few "
        "seconds during backfill saturates MongoDB"
    )


def test_should_run_blocks_within_interval():
    assert dedup.should_run(last_run_monotonic=1000.0, now_monotonic=1000.0 + 5) is False


def test_should_run_allows_after_interval():
    later = 1000.0 + dedup.MIN_DEDUP_INTERVAL_SECONDS + 1
    assert dedup.should_run(last_run_monotonic=1000.0, now_monotonic=later) is True


def test_should_run_allows_first_ever_run():
    assert dedup.should_run(last_run_monotonic=None, now_monotonic=1000.0) is True
