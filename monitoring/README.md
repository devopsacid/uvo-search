# UVO monitoring

Prometheus + Grafana for the local compose stack, defined entirely as code in this directory. Nothing here is applied to any live cluster (see [Kubernetes follow-up](#kubernetes-follow-up)).

```
monitoring/
  prometheus/prometheus.yml            scrape jobs (api, mcp, workers, self)
  prometheus/rules/uvo-alerts.yml      17 alert rules
  prometheus/rules/tests/              promtool unit tests
  grafana/provisioning/                datasource (uid `prometheus`) + dashboard provider (folder `UVO`)
  grafana/dashboards/                  3 dashboards, plain JSON
  scripts/validate.sh                  the same checks CI runs
  k8s/                                 optional, not applied anywhere
```

## Quick start

```bash
cp .env.example .env                      # first time only; fill the required secrets
docker compose up -d                      # the app stack
docker compose --profile monitoring up -d # adds prometheus + grafana
```

| What | URL | Login |
| ---- | --- | ----- |
| Grafana | http://127.0.0.1:3000 | `admin` / `$GRAFANA_ADMIN_PASSWORD`, or the **dev-only** default `uvo_grafana_dev` when it is blank |
| Prometheus | http://127.0.0.1:9090 | none (loopback only) |

Both ports are bound to `127.0.0.1`. Do not change that without adding authentication in front. Prometheus keeps 7 days of data in the `prometheus_data` volume.

The stack starts even before the API/MCP expose the new metrics: panels then show "No data" and the `up` targets for missing endpoints are red on http://127.0.0.1:9090/targets. Prometheus does not depend on the app services, so it also runs on its own.

Stop: `docker compose --profile monitoring down` (add `-v` to also drop the stored metrics and Grafana state).

## Dashboards

Open Grafana, then Dashboards, folder **UVO**. Each dashboard is organised in rows that each answer one question, uses short panel descriptions (hover the "i" icon), coloured thresholds (green fine, amber watch, red act) and a variable at the top to narrow the view. The "UVO dashboards" dropdown and the "Alert runbook" link are in the dashboard header.

| Dashboard | uid | Start here when | Variable |
| --------- | --- | --------------- | -------- |
| UVO · Pipeline health | `uvo-pipeline-health` | "Is ingestion running and keeping up?" Rows: anything broken now, streams keeping up, workers alive, alerts | `component` (worker) |
| UVO · API & search performance | `uvo-api-performance` | "Is the site slow or erroring?" Rows: healthy now, traffic and errors, latency, cache, MCP and process | `route`, `cache` |
| UVO · Data freshness | `uvo-data-freshness` | "Is the data up to date?" Rows: freshness per source, volume, trend | `source` |

Dashboards are provisioned from `grafana/dashboards/*.json` with `allowUiUpdates: false`, so edits in the UI are not saved to disk.

### Add or change a panel

1. Edit the panel in the Grafana UI (use a copy of the dashboard), then use Export, **Export as JSON**, and save the file.
2. Replace the file in `grafana/dashboards/`. Keep the `uid`, keep `version: 1`, no top-level `id`, datasource `{"type":"prometheus","uid":"prometheus"}`, a `unit` and a `description` on every stat, timeseries and bar gauge panel.
3. Run `monitoring/scripts/validate.sh`, then `docker compose --profile monitoring restart grafana` (the provider also rescans every 30 s).

## Validate and test the rules

```bash
monitoring/scripts/validate.sh        # needs docker and jq
```

This runs, using `prom/prometheus:v2.54.1` as the promtool provider: `promtool check config`, `promtool check rules`, `promtool test rules`, plus `jq` checks on the dashboards (valid JSON, unique uids, `prometheus` datasource uid, units, descriptions, unique panel ids). CI runs the same script in the `monitoring` job and then starts only Prometheus and Grafana to confirm that the three dashboards provision.

Run only the rule tests:

```bash
docker run --rm --entrypoint promtool -v "$PWD/monitoring/prometheus:/etc/prometheus:ro" \
  prom/prometheus:v2.54.1 test rules /etc/prometheus/rules/tests/uvo-alerts_test.yml
```

## Metrics scraped

| Target | Endpoint | Labels added |
| ------ | -------- | ------------ |
| `uvo-api` | `api:8001/metrics` | `job` |
| `uvo-mcp` | `mcp-server:8000/metrics` | `job` |
| `uvo-workers` | `extractor-vestnik:8091`, `extractor-crz:8092`, `extractor-ted:8093`, `extractor-itms:8094`, `ingestor:8095`, `dedup-worker:8096` | `job`, `component` (taken from the host name) |

Metric names are the contract defined in `docs/specs/2026-10-19-analytics-dashboards.md` section 8.1. Counters are exposed with the `_total` suffix (for example `uvo_worker_notices_written_total`). `uvo_worker_redis_connected` carries no `component` label of its own, so it relies on the scrape label.

## Alerts

There is no Alertmanager in the dev profile: alerts are visible at http://127.0.0.1:9090/alerts and on the **Pipeline health** dashboard (row 4). Every rule carries a `runbook` annotation pointing at its section below. Thresholds are starting points, stated in each rule's `description`; tune them after a week of data.

First two commands for most pipeline alerts:

```bash
uv run python -m uvo_pipeline health            # per-source counts, last ingestion age
docker compose logs --since 30m <service>        # service names from docker-compose.yml
```

The `db-monitor` agent produces the same view with ETAs for backfills.

### UvoWorkerDown
Critical, 5 min. Prometheus cannot scrape a worker's `/metrics`. The process is dead, restarting or its health port is unreachable. Check `docker compose ps`, then `docker compose logs --tail 100 <component>`. A worker that exits at start usually has bad Mongo/Redis/Neo4j settings. Related: [UvoWorkerRedisDisconnected](#uvoworkerredisdisconnected).

### UvoApiDown
Critical, 5 min. `api:8001/metrics` is unreachable. Check `docker compose ps api` and its logs; also `curl http://127.0.0.1:8001/health` (liveness) and `/readyz`. Until `install_metrics` is wired into the API the target is down by design, in which case this alert is expected.

### UvoMcpDown
Critical, 5 min. `mcp-server:8000/metrics` is unreachable. Same checks as the API on port 8000. The MCP server starts without Mongo/Neo4j, so a crash loop points at configuration rather than databases.

### UvoApiNotReady
Critical, 5 min. `uvo_ready{service="uvo-api"}` is 0: the bounded Mongo ping failed or a required Atlas Search index is missing or rebuilding. `curl -s http://127.0.0.1:8001/readyz` shows which check failed. Right after a fresh Mongo volume or an index definition change, a few minutes of 503 is normal while indexes build.

### UvoMcpNotReady
Critical, 5 min. Same meaning as the API alert for the MCP server (`/readyz` on port 8000).

### UvoStreamLagHigh
Warning, 15 min above 10 000. Entries are being produced faster than the ingestor consumes them. Check that the `ingestor` is up and its throughput (Pipeline health, "Notices written per second"). Extractors apply backpressure at `STREAM_HIGH_WATER`, so sustained lag also slows extraction. A big backfill can cause this legitimately.

### UvoStreamPendingStuck
Warning, 30 min above 500. Entries were delivered but never acknowledged, which means writes to Mongo or Neo4j keep failing; the ingestor acks only after both succeed. Read the ingestor logs for the exception, and check Neo4j and Mongo health. Entries retry via timed reclaim and are dead-lettered after `INGESTOR_MAX_DELIVERIES`.

### UvoDeadLettersGrowing
Warning when `notices:dead` grew in the last hour (critical variant `UvoDeadLettersGrowingFast` above +100). Entries failed repeatedly and were parked. Inspect with `redis-cli XLEN notices:dead` and `XRANGE notices:dead - + COUNT 5`, find the common error in the ingestor logs, fix the cause, then replay or discard deliberately. Note that the `health` CLI and `db-monitor` do not read `notices:dead` yet.

### UvoExtractorStalled
Warning, 10 min. An extractor that did succeed before has had no successful cycle for 3 h (vestnik, crz, itms) or 18 h (ted, which polls every 6 h). Check its logs for upstream errors (rate limits, API changes, timeouts), then compare with `uvo_pipeline health`. If a single cycle is slow rather than failing, check whether it is waiting on producer backpressure.

### UvoExtractorNeverSucceeded
Warning. An extractor process is older than 30 minutes and has never completed a cycle (success timestamp 0). Usually a configuration or credential problem, or a first full run that is simply long; read the logs for the first cycle.

### UvoWorkerErrorPersisting
Warning, 30 min. `uvo_worker_last_error` is 1: the worker's last cycle ended in an error and nothing has cleared it. Read the worker's `/health` JSON (ports 8091-8096) for `last_error`, and its logs.

### UvoWorkerRedisDisconnected
Critical, 5 min. A worker lost its Redis connection. Check `docker compose ps redis`, the Redis password (`REDIS_PASSWORD`) and the worker logs. Streams stop flowing for that worker until it reconnects.

### UvoSourceStale
Warning. A source (vestnik, crz, ted, itms) has no newly ingested notice for more than 48 h, or never ingested (timestamp 0). The legacy `uvo` source is excluded. Run `uv run python -m uvo_pipeline health` and check the matching extractor ([UvoExtractorStalled](#uvoextractorstalled)). Some sources can legitimately be quiet over holidays.

### UvoApiErrorRate
Warning, 10 min. More than 5% of API requests returned 5xx while traffic is above 0.1 req/s. On the **API performance** dashboard, the "Responses by status class" and route panels show where. Typical causes: Mongo or Neo4j outage (`BackendUnavailable` maps to 503), or a bad deploy. Check `/readyz` and the API logs.

### UvoApiSlow
Warning, 10 min. p95 latency above 2 s on analytics, contracts or search routes. Use "p95 latency by route group" and "Cached call p95 by cache" to find the slow aggregate; check Mongo load and whether the cache hit ratio dropped ([UvoCacheHitRateLow](#uvocachehitratelow)). Search index rebuilds also degrade search latency.

### UvoCacheHitRateLow
Info, 30 min below 50% with real traffic. The TTL cache is not absorbing load, so Mongo takes the full cost of aggregates. Look at the per-cache hit ratio; common causes are a restart (cold cache), filter combinations with high cardinality, or a TTL that is too short.

## Kubernetes follow-up

Not done here and not applied anywhere. Production runs in the `stubarag-infra` repository; this repository only supplies the inputs:

- Scrape: `ServiceMonitor`/`PodMonitor` objects (or scrape annotations) for the API, MCP and each worker, keeping the `job` values (`uvo-api`, `uvo-mcp`, `uvo-workers`) and the `component` label (`extractor-vestnik`, `extractor-crz`, `extractor-ted`, `extractor-itms`, `ingestor`, `dedup-worker`).
- Dashboards: a ConfigMap labelled `grafana_dashboard: "1"` generated from `grafana/dashboards/*.json`.
- Rules: a `PrometheusRule` generated from `prometheus/rules/uvo-alerts.yml`.
- A NetworkPolicy must let the monitoring namespace reach the `/metrics` ports. The API's `/metrics` is outside `/api`, so the public Traefik route does not expose it.

`k8s/` contains a kustomization that renders the dashboard and rule ConfigMaps; see `k8s/README.md`.
