"""Wildcard queries must not become unbounded term-dictionary scans.

Atlas resolves a `wildcard` operator with allowAnalyzedField against the term
dictionary of every analyzed path. With no literal prefix that is a full scan
across four fields, reachable from an unauthenticated endpoint.
"""

from uvo_mcp.search_query import build_search_stage

PATHS = ["title", "description"]


def test_leading_wildcard_is_rejected():
    """A leading * forces a full term-dictionary scan across every analyzed field."""
    stage = build_search_stage("*", PATHS)
    assert "wildcard" not in str(stage), "bare leading wildcard must not reach Atlas"


def test_short_prefix_wildcard_is_rejected():
    stage = build_search_stage("a*", PATHS)
    assert "wildcard" not in str(stage)


def test_wildcard_with_sufficient_prefix_is_allowed():
    stage = build_search_stage("bratisl*", PATHS)
    assert "wildcard" in str(stage)


def test_question_mark_needs_a_prefix_too():
    assert "wildcard" not in str(build_search_stage("a?", PATHS))
    assert "wildcard" in str(build_search_stage("bratisl?", PATHS))


def test_plain_text_query_unaffected():
    stage = build_search_stage("verejne obstaravanie", PATHS)
    assert "wildcard" not in str(stage)
    assert stage != {}


def test_short_wildcard_still_returns_a_usable_stage():
    """Rejected wildcards fall through to ordinary text search, not an error."""
    stage = build_search_stage("a*", PATHS)
    assert "compound" in stage
