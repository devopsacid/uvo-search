# UVO Search — Data Pipeline

## Overview

The data pipeline ingests Slovak public procurement data from four sources into local databases, enabling the MCP server to answer queries without real-time API calls. Data is stored in MongoDB (primary document store) and Neo4j (graph relationships for network analysis).

The pipeline runs as a Docker Compose service. The default mode (`recent`) fetches the past 365 days on startup. Historical backfill from 2014 is available as an on-demand command.

---

## Architecture

```
[data.gov.sk CKAN]     [UVOstat.sk API]     [Ekosystem CRZ]     [TED EU API]
       |                      |                    |                   |
  catalog/ckan.py      extractors/uvostat.py  extractors/crz.py  extractors/ted.py
  extractors/vestnik_xml.py
       |                      |                    |                   |
       +----------------------+--------------------+-------------------+
                              |
                    transformers/<source>.py
                    (-> CanonicalNotice)
                              |
                    +---------+---------+
                    |                   |
               loaders/mongo.py    loaders/neo4j.py
                    |                   |
               MongoDB             Neo4j
               uvo_search          (graph)
                    |                   |
                    +---------+---------+
                              |
                     MCP Server (port 8000)
                     src/uvo_mcp/
```

---

## Data Sources

| Source | Type | Auth | Update Frequency | Coverage |
|---|---|---|---|---|
| UVO.gov.sk Vestník NKOD | SPARQL + JSON download | None | Daily (working days) | 2016–present |
| UVOstat.sk API | REST API | `ApiToken` header | 24h–7d | 2014–present |
| Ekosystem CRZ | REST API | Optional token | Continuous | 2011–present |
| TED EU API | REST API | None | Daily | All above-threshold |

**Note**: Vestník source changed from CKAN (data.gov.sk) to NKOD SPARQL (data.slovensko.sk) as CKAN was deprecated in favor of React SPA. See [plan-vestnik-nkod.md](plan-vestnik-nkod.md) for implementation details.

---

## Pipeline Modes

### Recent mode (default)
```bash
docker compose run --rm pipeline --mode=recent
# or just start the pipeline container
docker compose up pipeline
```
- Fetches data from the last 365 days (configurable via `RECENT_DAYS`)
- Uses checkpoint from MongoDB to start from last successful run
- Runs once and exits (`restart: "no"` in Docker Compose)

### Historical backfill
```bash
docker compose run --rm pipeline --mode=historical
```
- Full backfill from `HISTORICAL_FROM_YEAR` (default: 2014)
- May take several hours depending on data volume
- Safe to re-run — all writes are idempotent upserts

### Dry run
```bash
docker compose run --rm pipeline --mode=recent --dry-run
```
- Skips DB connections
- Useful for testing configuration

---

## Common Data Schema

All sources normalize to `CanonicalNotice` before any DB write. See `src/uvo_pipeline/models.py`.

**Deduplication keys per source:**

| Source | Primary dedup key | Notes |
|---|---|---|
| `vestnik` | `(source="vestnik", source_id=notice_id)` | notice_id from XML `cbc:ID` |
| `uvostat` | `(source="uvostat", source_id=str(id))` | numeric API ID |
| `crz` | `(source="crz", source_id=str(id))` | Ekosystem contract ID |
| `ted` | `(source="ted", source_id=ND_OJ)` | TED official journal number |

**Cross-source deduplication:** After each pipeline run, notices with matching `(procurer_ico, cpv_code)` from different sources are linked via a shared `canonical_id` field. Links are stored in the `cross_source_matches` collection.

---

## MongoDB Collections

**Database:** `uvo_search`

| Collection | Dedup key | Key indexes |
|---|---|---|
| `notices` | `(source, source_id)` unique | `publication_date desc`, `procurer.ico`, `cpv_code`, `awards.supplier.ico`, text on `title`+`description` |
| `procurers` | `ico` unique (sparse) + `name_slug` unique | text on `name` |
| `suppliers` | `ico` unique (sparse) + `name_slug` unique | text on `name` |
| `cross_source_matches` | `canonical_id` | `notice_ids` array |
| `pipeline_state` | `source` unique | — |
| `ckan_packages` | `package_id` unique | `last_modified desc` |

---

## Neo4j Graph Model

### Nodes

| Label | Key property | Description |
|---|---|---|
| `Procurer` | `ico` | Contracting authority |
| `Supplier` | `ico` | Awarded contractor |
| `Notice` | `(source, source_id)` | Procurement notice/award |
| `CPVCode` | `code` | Common Procurement Vocabulary code |
| `Contract` | `crz_contract_id` | CRZ contract record |

### Relationships

```cypher
(:Procurer)-[:ISSUED {publication_date}]->(:Notice)
(:Notice)-[:AWARDED_TO {value, currency, award_date}]->(:Supplier)
(:Notice)-[:CLASSIFIED_BY]->(:CPVCode)
(:Notice)-[:SAME_AS {confidence}]->(:Notice)
(:Notice)-[:RESULTED_IN]->(:Contract)
```

### Example queries

Find top suppliers for a contracting authority:
```cypher
MATCH (:Procurer {ico: "12345678"})-[:ISSUED]->(n:Notice)-[r:AWARDED_TO]->(s:Supplier)
RETURN s.name, count(n) AS contracts, sum(r.value) AS total
ORDER BY total DESC LIMIT 10
```

Find organisations connected through shared contracts:
```cypher
MATCH (start {ico: "12345678"})-[*1..2]-(related)
WHERE (related:Procurer OR related:Supplier)
RETURN DISTINCT related.name, related.ico, labels(related)[0]
```

---

## Running the Pipeline

```bash
# First-time setup (starts MongoDB and Neo4j)
docker compose up mongo neo4j -d

# Run recent pipeline (fetches last 365 days)
docker compose run --rm pipeline --mode=recent

# Historical backfill (from 2014)
docker compose run --rm pipeline --mode=historical

# Check results in MongoDB
docker compose exec mongo mongosh -u uvo -p $MONGO_PASSWORD uvo_search \
  --eval "db.notices.countDocuments({})"

# Open Neo4j Browser
# http://localhost:7474  (user: neo4j, password from NEO4J_PASSWORD env var)
```

---

## Checkpoint and Incremental Runs

Checkpoints are stored in the `pipeline_state` MongoDB collection (key: `source = "pipeline"`).

On `--mode=recent`, if a checkpoint exists with a date more recent than `today - RECENT_DAYS`, the pipeline uses the checkpoint date as `from_date` instead.

To reset the checkpoint (force full re-fetch in recent mode):
```javascript
// In mongosh:
db.pipeline_state.deleteOne({source: "pipeline"})
```

---

## Environment Variables

Add these to `.env`:

```bash
# MongoDB
MONGO_PASSWORD=changeme
MONGODB_URI=mongodb://uvo:changeme@mongo:27017

# Neo4j
NEO4J_PASSWORD=changeme
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j

# Pipeline behaviour
PIPELINE_MODE=recent        # recent | historical
RECENT_DAYS=365
HISTORICAL_FROM_YEAR=2014
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `401 Unauthorized` from UVOstat | Token expired or missing | Check `UVOSTAT_API_TOKEN` in `.env` |
| `429 Too Many Requests` from CRZ | Rate limit exceeded | Lower `CRZ_RATE_LIMIT` (default: 55/min) |
| ZIP download timeout | Large Vestník package | Increase `REQUEST_TIMEOUT` |
| Neo4j OOM | Heap too small | Set `NEO4J_server_memory_heap_max__size: 2g` |
| Pipeline exits with 0 notices | No data in date range | Check `from_date` and checkpoint |

---

## Adding a New Data Source

1. Add extractor: `src/uvo_pipeline/extractors/<source>.py` — async generator yielding raw dicts
2. Add transformer: `src/uvo_pipeline/transformers/<source>.py` — `transform_<entity>(raw) -> CanonicalNotice`
3. Add to orchestrator: `src/uvo_pipeline/orchestrator.py` — add extraction block in `run()`
4. Add tests: `tests/pipeline/extractors/test_<source>.py`, `tests/pipeline/transformers/test_<source>.py`
5. Add checkpoint key to `pipeline_state` if the source needs incremental tracking
