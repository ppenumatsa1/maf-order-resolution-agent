#!/usr/bin/env bash
set -euo pipefail

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required binary: $1"
    exit 1
  }
}

require_bin az
require_bin jq

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-maf-ora-foundry-public-dev2}"
APPLICATION_INSIGHTS_NAME="${APPLICATION_INSIGHTS_NAME:-maffnd-mon-bfscpfhjr7sp4-appi}"
LOOKBACK_MINUTES="${TELEMETRY_LOOKBACK_MINUTES:-30}"
MAX_ATTEMPTS="${TELEMETRY_MAX_ATTEMPTS:-12}"
EVIDENCE_FILE="${HOSTED_E2E_EVIDENCE_FILE:-backend/.foundry/results/hosted-e2e-evidence.json}"

[[ -f "$EVIDENCE_FILE" ]] || {
  echo "Hosted E2E evidence is required: $EVIDENCE_FILE"
  exit 1
}

started_at="$(jq -r '.started_at // .generated_at // empty' "$EVIDENCE_FILE")"
mapfile -t conversation_ids < <(
  jq -r '
    [.low_risk_thread_id, .approved_thread_id]
    | .[]
    | select(type == "string" and length > 0)
  ' "$EVIDENCE_FILE"
)

[[ -n "$started_at" && "${#conversation_ids[@]}" -gt 0 ]] || {
  echo "Hosted E2E evidence does not contain a timestamp and conversation IDs."
  exit 1
}

conversation_ids_json="$(printf '%s\n' "${conversation_ids[@]}" | jq -R . | jq -sc .)"

query=$(cat <<EOF
let e2eStartedAt = todatetime('${started_at}');
let conversationIds = dynamic(${conversation_ids_json});
union isfuzzy=true traces, dependencies, requests, customEvents, exceptions
| where timestamp between (e2eStartedAt .. now())
| extend dimensions = tostring(customDimensions)
| mv-expand conversationId = conversationIds
| where dimensions has tostring(conversationId)
| summarize
    matched_count = dcount(tostring(conversationId)),
    telemetry_rows = count(),
    exception_rows = countif(itemType == "exception")
EOF
)

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  result="$(
    az monitor app-insights query \
      --resource-group "$RESOURCE_GROUP" \
      --app "$APPLICATION_INSIGHTS_NAME" \
      --analytics-query "$query" \
      -o json
  )"
  matched_count="$(echo "$result" | jq -r '.tables[0].rows[0][0] // 0')"
  telemetry_rows="$(echo "$result" | jq -r '.tables[0].rows[0][1] // 0')"
  exception_rows="$(echo "$result" | jq -r '.tables[0].rows[0][2] // 0')"
  if [[ "$telemetry_rows" -gt 0 && "$matched_count" -eq "${#conversation_ids[@]}" && "$exception_rows" -eq 0 ]]; then
    echo "Application Insights telemetry check passed: ${telemetry_rows} correlated rows for ${matched_count} hosted E2E conversations."
    exit 0
  fi
  echo "Awaiting correlated telemetry (attempt ${attempt}/${MAX_ATTEMPTS}; rows=${telemetry_rows}, conversations=${matched_count}/${#conversation_ids[@]}, exceptions=${exception_rows})."
  sleep 15
done

echo "Application Insights telemetry was not correlated to all current hosted E2E conversations within the bounded wait."
exit 1
