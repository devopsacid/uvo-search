#!/usr/bin/env bash
# Validate the monitoring stack offline: the same checks CI runs.
#   - promtool check config / check rules / test rules (prom/prometheus image)
#   - dashboard JSON sanity via jq (uids, datasource, units, schema)
# Requires: docker, jq. Run from anywhere.
set -euo pipefail

PROM_IMAGE="${PROM_IMAGE:-prom/prometheus:v2.54.1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROM_DIR="${ROOT}/prometheus"
DASH_DIR="${ROOT}/grafana/dashboards"

log() { printf '[validate] %s\n' "$*"; }
fail() { printf '[validate] ERROR: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || fail "docker is required for promtool"
command -v jq >/dev/null || fail "jq is required for dashboard checks"

promtool() {
  docker run --rm --entrypoint promtool -v "${PROM_DIR}:/etc/prometheus:ro" "${PROM_IMAGE}" "$@"
}

log "promtool check config"
promtool check config /etc/prometheus/prometheus.yml

log "promtool check rules"
promtool check rules /etc/prometheus/rules/uvo-alerts.yml

log "promtool test rules"
promtool test rules /etc/prometheus/rules/tests/uvo-alerts_test.yml

log "dashboards: JSON + structure"
shopt -s nullglob
files=("${DASH_DIR}"/*.json)
[ "${#files[@]}" -gt 0 ] || fail "no dashboards found in ${DASH_DIR}"

for f in "${files[@]}"; do
  jq -e . "${f}" >/dev/null || fail "${f}: invalid JSON"
  jq -e '(.uid | type == "string" and length > 0)
         and (.title | type == "string" and length > 0)
         and (has("id") | not)
         and .version == 1
         and .schemaVersion >= 39' "${f}" >/dev/null \
    || fail "${f}: needs non-empty uid/title, no id, version 1, schemaVersion >= 39"

  # every datasource reference must be the provisioned uid `prometheus`
  bad_ds=$(jq -r '[.. | objects | select(has("datasource")) | .datasource
                   | select(type == "object" and .type == "prometheus" and .uid != "prometheus")] | length' "${f}")
  [ "${bad_ds}" = "0" ] || fail "${f}: ${bad_ds} prometheus datasource reference(s) not using uid 'prometheus'"
  jq -e '[.panels[] | (.datasource, (.targets[]?.datasource)) | select(type == "string")] | length == 0' "${f}" >/dev/null \
    || fail "${f}: string datasource references are not allowed (use uid object)"

  # units on every data panel (table units live in overrides and are exempt)
  missing=$(jq -r '[.panels[] | select(.type == "stat" or .type == "timeseries" or .type == "bargauge")
                    | select(.fieldConfig.defaults.unit == null) | .title] | join(", ")' "${f}")
  [ -z "${missing}" ] || fail "${f}: panels without a unit: ${missing}"

  # every non-row panel carries a description
  nodesc=$(jq -r '[.panels[] | select(.type != "row" and ((.description // "") == "")) | .title] | join(", ")' "${f}")
  [ -z "${nodesc}" ] || fail "${f}: panels without a description: ${nodesc}"

  # unique panel ids
  jq -e '[.panels[].id] | (length == (unique | length))' "${f}" >/dev/null || fail "${f}: duplicate panel ids"
done

dups=$(jq -r '.uid' "${files[@]}" | sort | uniq -d)
[ -z "${dups}" ] || fail "duplicate dashboard uid(s): ${dups}"

log "OK: ${#files[@]} dashboards, rules and config valid"
