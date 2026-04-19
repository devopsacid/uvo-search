from uvo_mcp.search_query import build_search_stage


def test_empty_query_uses_exists():
    stage = build_search_stage("", ["name"])
    assert stage == {"exists": {"path": "name"}}


def test_quoted_phrase_uses_phrase_operator():
    stage = build_search_stage('"Fakulta elektrotechniky"', ["name"])
    assert stage == {
        "phrase": {"query": "Fakulta elektrotechniky", "path": ["name"]}
    }


def test_wildcard_star_uses_wildcard_operator():
    stage = build_search_stage("fakul*", ["name"])
    assert stage == {
        "wildcard": {"query": "fakul*", "path": ["name"], "allowAnalyzedField": True}
    }


def test_question_mark_uses_wildcard_operator():
    stage = build_search_stage("fak?lta", ["name"])
    assert stage["wildcard"]["query"] == "fak?lta"


def test_plain_query_uses_compound_autocomplete_plus_text():
    stage = build_search_stage("fakulta", ["name"])
    should = stage["compound"]["should"]
    assert {"autocomplete": {"query": "fakulta", "path": "name", "fuzzy": {"maxEdits": 1}}} in should
    assert {"text": {"query": "fakulta", "path": ["name"]}} in should


def test_plain_query_multi_path_uses_first_path_for_autocomplete():
    stage = build_search_stage("fakulta", ["title", "description"])
    should = stage["compound"]["should"]
    auto = next(s for s in should if "autocomplete" in s)
    assert auto["autocomplete"]["path"] == "title"
    text = next(s for s in should if "text" in s)
    assert text["text"]["path"] == ["title", "description"]
