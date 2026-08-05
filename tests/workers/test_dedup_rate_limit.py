"""Dedup must not re-run on every batch — it is an O(n^2) scan."""

import pytest

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


# --- next_debounced_action: the _timer wiring around should_run/debounce ---
#
# Regression coverage for the drop-vs-defer bug: the old inline code cleared
# `pending` as soon as the debounce window closed, *before* checking the
# MIN_DEDUP_INTERVAL_SECONDS floor. If the floor blocked, `pending` was
# already gone — the deferred run was silently dropped until either another
# notices:written message arrived or the 1-hour interval fallback fired.


def test_within_debounce_window_defers_without_touching_pending_state():
    action, sleep_for = dedup.next_debounced_action(
        debounce_remaining=2.5, last_dedup_run=None, now=1000.0
    )
    assert action == "sleep_debounce"
    assert sleep_for == 2.5


def test_debounce_elapsed_and_floor_open_runs_immediately():
    action, sleep_for = dedup.next_debounced_action(
        debounce_remaining=0.0,
        last_dedup_run=1000.0 - dedup.MIN_DEDUP_INTERVAL_SECONDS - 1,
        now=1000.0,
    )
    assert action == "run"
    assert sleep_for is None


def test_debounce_elapsed_but_floor_still_closed_defers_not_drops():
    """This is the bug: the caller must NOT clear `pending` for this action,
    or the deferred run is lost until the next write or the 1-hour fallback."""
    last_dedup_run = 1000.0
    now = last_dedup_run + 10  # floor is 300s; only 10s have passed
    action, sleep_for = dedup.next_debounced_action(
        debounce_remaining=0.0, last_dedup_run=last_dedup_run, now=now
    )
    assert action == "sleep_floor"
    assert sleep_for == pytest.approx(dedup.MIN_DEDUP_INTERVAL_SECONDS - 10)


def test_floor_defer_sleep_is_never_negative_or_zero():
    """A near-zero remaining floor must still yield a positive sleep so the
    timer loop doesn't spin a tight busy-loop."""
    last_dedup_run = 1000.0
    now = last_dedup_run + dedup.MIN_DEDUP_INTERVAL_SECONDS - 0.001
    _action, sleep_for = dedup.next_debounced_action(
        debounce_remaining=0.0, last_dedup_run=last_dedup_run, now=now
    )
    assert sleep_for > 0
