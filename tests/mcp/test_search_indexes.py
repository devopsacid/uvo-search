from uvo_mcp.search_indexes import INDEX_DEFINITIONS


def test_all_three_collections_present():
    assert set(INDEX_DEFINITIONS.keys()) == {"procurers", "suppliers", "notices"}


def test_custom_analyzer_registered_per_index():
    for spec in INDEX_DEFINITIONS.values():
        analyzers = spec["definition"]["analyzers"]
        names = [a["name"] for a in analyzers]
        assert "sk_folding" in names
        filters = next(a for a in analyzers if a["name"] == "sk_folding")["tokenFilters"]
        types = [f["type"] for f in filters]
        assert "lowercase" in types and "icuFolding" in types


def test_procurers_has_autocomplete_on_name():
    fields = INDEX_DEFINITIONS["procurers"]["definition"]["mappings"]["fields"]
    name_types = [f["type"] for f in fields["name"]]
    assert "autocomplete" in name_types
    assert "string" in name_types


def test_notices_fields_include_title_and_cpv_as_token():
    fields = INDEX_DEFINITIONS["notices"]["definition"]["mappings"]["fields"]
    assert fields["title"]["type"] == "string"
    assert fields["cpv_code"]["type"] == "token"
    assert fields["publication_date"]["type"] == "date"
