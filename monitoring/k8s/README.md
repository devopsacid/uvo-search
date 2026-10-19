# monitoring/k8s — NOT APPLIED ANYWHERE

Input for the `stubarag-infra` repository, which owns the production cluster (Helm charts, Longhorn, Traefik, ESO). Nothing in this directory is deployed from this repository and no pipeline here applies it.

`kustomization.yaml` renders:

- a ConfigMap `uvo-grafana-dashboards` from `../grafana/dashboards/*.json`, labelled `grafana_dashboard: "1"` for the Grafana sidecar;
- a ConfigMap `uvo-prometheus-rules` holding `../prometheus/rules/uvo-alerts.yml`, labelled `app.kubernetes.io/part-of: uvo-search`.

Preview locally (no cluster needed):

```bash
kubectl kustomize --load-restrictor LoadRestrictionsNone monitoring/k8s
```

The flag is needed because the sources live in the sibling directories (`../grafana`, `../prometheus`).

`PrometheusRule` objects wrap the same `groups:` content under `spec:`; stubarag-infra can template that from the ConfigMap or copy the groups. Scrape objects (`ServiceMonitor`/`PodMonitor`) are left to the chart because they depend on its Service and Pod labels. Keep the `job` and `component` label values documented in `../README.md`.
