import copy

import pytest

from uvo_core.adapters.mongo.search_indexes import (
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
    # publication_date is stored as an ISO string (model_dump(mode="json")), so the
    # `date` mapping alone indexes nothing; `token` backs $search range + sort.
    pub_types = [f["type"] for f in fields["publication_date"]]
    assert "token" in pub_types and "date" in pub_types


def test_notices_filter_fields_mapped_as_token():
    # Every compound.filter clause search_procurements emits needs a token
    # mapping, otherwise equals/in/range silently match nothing.
    fields = INDEX_DEFINITIONS["notices"]["definition"]["mappings"]["fields"]
    assert fields["notice_type"]["type"] == "token"
    assert fields["procurer"]["fields"]["ico"]["type"] == "token"
    assert fields["procurer"]["fields"]["name"]["type"] == "string"
    supplier = fields["awards"]["fields"]["supplier"]["fields"]
    assert supplier["ico"]["type"] == "token"
    assert supplier["name"]["type"] == "string"


def test_notices_text_fields_keep_sk_folding_analyzer():
    definition = INDEX_DEFINITIONS["notices"]["definition"]
    assert definition["analyzer"] == "sk_folding"
    assert definition["searchAnalyzer"] == "sk_folding"


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


# --- readiness probe (A13) -------------------------------------------------


class _ListingDB:
    """db[coll].list_search_indexes() yields the configured index docs per collection."""

    def __init__(self, per_coll, fail=False):
        self._per_coll = per_coll
        self._fail = fail
        self.calls = 0

    def __getitem__(self, coll):
        outer = self

        class _Coll:
            async def list_search_indexes(self_inner):
                outer.calls += 1
                if outer._fail:
                    raise RuntimeError("mongot down")
                for i in outer._per_coll.get(coll, []):
                    yield i

        return _Coll()


def _all_present():
    return {c: [{"name": "default", "queryable": True}] for c in INDEX_DEFINITIONS}


@pytest.mark.asyncio
async def test_missing_search_indexes_empty_when_all_present():
    from uvo_core.adapters.mongo.search_indexes import missing_search_indexes

    assert await missing_search_indexes(_ListingDB(_all_present())) == []


@pytest.mark.asyncio
async def test_missing_search_indexes_reports_absent_and_unqueryable():
    from uvo_core.adapters.mongo.search_indexes import missing_search_indexes

    per = _all_present()
    per["notices"] = []
    per["suppliers"] = [{"name": "default", "queryable": False}]
    assert sorted(await missing_search_indexes(_ListingDB(per))) == [
        "notices.default",
        "suppliers.default",
    ]


@pytest.mark.asyncio
async def test_missing_search_indexes_all_missing_when_server_errors():
    from uvo_core.adapters.mongo.search_indexes import missing_search_indexes

    missing = await missing_search_indexes(_ListingDB({}, fail=True))
    assert len(missing) == len(INDEX_DEFINITIONS)


@pytest.mark.asyncio
async def test_probe_caches_result_within_ttl_then_refreshes():
    from uvo_core.adapters.mongo.search_indexes import SearchIndexProbe

    now = {"t": 100.0}
    probe = SearchIndexProbe(ttl=30.0, clock=lambda: now["t"])
    db = _ListingDB(_all_present())

    assert await probe.ready(db) is True
    calls_after_first = db.calls
    now["t"] = 110.0
    assert await probe.ready(db) is True
    assert db.calls == calls_after_first  # served from cache

    now["t"] = 140.0
    assert await probe.ready(db) is True
    assert db.calls > calls_after_first  # ttl elapsed -> re-checked


@pytest.mark.asyncio
async def test_ensure_indexes_logs_error_on_failure(caplog):
    import logging

    class _Boom:
        def __getitem__(self, coll):
            raise RuntimeError("boom")

        async def command(self, *a, **kw):
            return {}

    with caplog.at_level(logging.ERROR):
        await ensure_indexes(_Boom())
    assert any(r.levelno == logging.ERROR for r in caplog.records)


# --- fresh-DB provisioning retry (QA bug: readiness never recovered) --------


class _FailingCollection(_FakeCollection):
    def __init__(self, failures):
        super().__init__([])
        self._failures = failures

    async def create_search_index(self, spec):
        if self._failures > 0:
            self._failures -= 1
            raise RuntimeError("Collection 'uvo_search.notices' does not exist")
        await super().create_search_index(spec)


@pytest.mark.asyncio
async def test_ensure_indexes_reports_failure_and_success():
    from uvo_core.adapters.mongo import search_indexes

    colls = {c: _FakeCollection([]) for c in INDEX_DEFINITIONS}
    assert await search_indexes.ensure_indexes(_FakeDB(colls)) is True

    colls["notices"] = _FailingCollection(failures=1)
    assert await search_indexes.ensure_indexes(_FakeDB(colls)) is False


@pytest.mark.asyncio
async def test_ensure_indexes_creates_missing_collections_first():
    class _DB(_FakeDB):
        def __init__(self, per_coll, existing):
            super().__init__(per_coll)
            self.existing = list(existing)
            self.created_collections = []

        async def list_collection_names(self):
            return list(self.existing)

        async def create_collection(self, name):
            self.created_collections.append(name)

    colls = {c: _FakeCollection([]) for c in INDEX_DEFINITIONS}
    db = _DB(colls, existing=["procurers"])
    await ensure_indexes(db)
    assert sorted(db.created_collections) == ["notices", "suppliers"]


@pytest.mark.asyncio
async def test_retry_ensure_indexes_retries_with_backoff_until_success(caplog):
    from uvo_core.adapters.mongo.search_indexes import retry_ensure_indexes

    results = iter([False, RuntimeError("boom"), False, True])
    calls = []

    async def ensure(db):
        calls.append(db)
        outcome = next(results)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    with caplog.at_level("WARNING"):
        await retry_ensure_indexes(
            object(), ensure=ensure, interval=30.0, max_interval=100.0, sleep=fake_sleep
        )

    assert len(calls) == 4
    assert sleeps == [30.0, 60.0, 100.0, 100.0]  # sleep-then-try, exponential, capped
    assert sum(r.levelname == "WARNING" for r in caplog.records) == 3
