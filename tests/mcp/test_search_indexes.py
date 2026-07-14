import copy

import pytest

from uvo_mcp.search_indexes import (
    INDEX_DEFINITIONS,
    definition_is_current,
    ensure_indexes,
)


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
    title_types = [f["type"] for f in fields["title"]]
    assert "string" in title_types
    assert fields["cpv_code"]["type"] == "token"
    assert fields["publication_date"]["type"] == "date"


def test_notices_title_has_autocomplete_for_search_operator():
    # build_search_stage emits an `autocomplete` operator on path[0] (title);
    # the index must map an autocomplete subfield there or $search 500s with
    # "autocomplete index field definition not present at path title".
    fields = INDEX_DEFINITIONS["notices"]["definition"]["mappings"]["fields"]
    title_types = [f["type"] for f in fields["title"]]
    assert "autocomplete" in title_types


def _live_from_desired(desired):
    """Mimic how Atlas enriches a stored definition: add options to string
    fields and default `dynamic` on document mappings."""
    if isinstance(desired, dict):
        out = {k: _live_from_desired(v) for k, v in desired.items()}
        if out.get("type") == "string":
            out.update(indexOptions="offsets", store=True, norms="include")
        if out.get("type") == "document":
            out.setdefault("dynamic", False)
        return out
    if isinstance(desired, list):
        return [_live_from_desired(v) for v in desired]
    return desired


def test_definition_is_current_true_for_enriched_live_copy():
    desired = INDEX_DEFINITIONS["notices"]["definition"]
    live = _live_from_desired(desired)
    # extra keys / reordering / enrichment must not be seen as drift
    assert definition_is_current(desired, live) is True


def test_definition_is_current_detects_missing_autocomplete_on_title():
    desired = INDEX_DEFINITIONS["notices"]["definition"]
    live = _live_from_desired(desired)
    # simulate the drift we hit in prod: title mapped as a plain string only
    live["mappings"]["fields"]["title"] = {
        "type": "string",
        "indexOptions": "offsets",
        "store": True,
        "norms": "include",
    }
    assert definition_is_current(desired, live) is False


def test_definition_is_current_detects_changed_scalar():
    desired = {"mappings": {"fields": {"cpv_code": {"type": "token"}}}}
    live = {"mappings": {"fields": {"cpv_code": {"type": "string"}}}}
    assert definition_is_current(desired, live) is False


class _FakeCollection:
    def __init__(self, existing):
        self._existing = existing
        self.created = []
        self.updated = []

    async def list_search_indexes(self):
        for i in self._existing:
            yield i

    async def create_search_index(self, spec):
        self.created.append(spec)

    async def update_search_index(self, name, definition):
        self.updated.append((name, definition))


class _FakeDB:
    def __init__(self, per_coll):
        self._per_coll = per_coll
        self.commanded = []

    def __getitem__(self, coll):
        return self._per_coll[coll]

    async def command(self, *args, **kwargs):
        self.commanded.append((args, kwargs))


@pytest.mark.asyncio
async def test_ensure_indexes_creates_when_missing():
    colls = {c: _FakeCollection([]) for c in INDEX_DEFINITIONS}
    db = _FakeDB(colls)
    await ensure_indexes(db)
    assert colls["notices"].created and not colls["notices"].updated


@pytest.mark.asyncio
async def test_ensure_indexes_updates_on_drift():
    colls = {}
    for c, spec in INDEX_DEFINITIONS.items():
        live = _live_from_desired(spec["definition"])
        if c == "notices":
            # drift: title lost its autocomplete subfield
            live["mappings"]["fields"]["title"] = {"type": "string"}
        colls[c] = _FakeCollection([{"name": "default", "latestDefinition": live}])
    db = _FakeDB(colls)
    await ensure_indexes(db)
    assert colls["notices"].updated and not colls["notices"].created
    name, definition = colls["notices"].updated[0]
    assert name == "default"
    assert definition == INDEX_DEFINITIONS["notices"]["definition"]


@pytest.mark.asyncio
async def test_ensure_indexes_noop_when_current():
    colls = {}
    for c, spec in INDEX_DEFINITIONS.items():
        live = _live_from_desired(spec["definition"])
        colls[c] = _FakeCollection([{"name": "default", "latestDefinition": live}])
    db = _FakeDB(colls)
    await ensure_indexes(db)
    for c in INDEX_DEFINITIONS:
        assert not colls[c].created
        assert not colls[c].updated


def test_definition_deepcopy_not_mutated_by_check():
    desired = INDEX_DEFINITIONS["notices"]["definition"]
    snapshot = copy.deepcopy(desired)
    definition_is_current(desired, _live_from_desired(desired))
    assert desired == snapshot
