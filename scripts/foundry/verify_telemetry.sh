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

: "${AZURE_RESOURCE_GROUP:?AZURE_RESOURCE_GROUP is required}"
: "${APPLICATION_INSIGHTS_NAME:?APPLICATION_INSIGHTS_NAME is required}"

MAX_ATTEMPTS="${TELEMETRY_MAX_ATTEMPTS:-24}"
POLL_SECONDS="${TELEMETRY_POLL_SECONDS:-15}"
EVIDENCE_FILE="${HOSTED_E2E_EVIDENCE_FILE:-backend/.foundry/results/hosted-e2e-evidence.json}"
RESULT_FILE="${TELEMETRY_RESULT_FILE:-backend/.foundry/results/telemetry-verification.json}"

[[ -f "$EVIDENCE_FILE" ]] || {
  echo "Hosted E2E evidence is required: $EVIDENCE_FILE"
  exit 1
}

started_at="$(jq -r '.started_at // .generated_at // empty' "$EVIDENCE_FILE")"
mapfile -t conversation_ids < <(
  jq -r '
    (
      .conversation_ids
      // [
        .low_risk_thread_id,
        (.high_risk_thread_id // .approved_thread_id),
        (.damaged_item_thread_id // .damaged_thread_id)
      ]
    )
    | .[]
    | select(type == "string" and length > 0)
  ' "$EVIDENCE_FILE"
)

[[ -n "$started_at" && "${#conversation_ids[@]}" -ge 3 ]] || {
  echo "Hosted E2E evidence must contain a timestamp and all three scenario conversations."
  exit 1
}

mkdir -p "$(dirname "$RESULT_FILE")"
conversation_ids_json="$(printf '%s\n' "${conversation_ids[@]}" | jq -R . | jq -sc 'unique')"

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
    trace_rows = countif(itemType == "trace"),
    dependency_rows = countif(itemType == "dependency"),
    request_rows = countif(itemType == "request"),
    exception_rows = countif(itemType == "exception")
EOF
)

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  result="$(
    az monitor app-insights query \
      --resource-group "$AZURE_RESOURCE_GROUP" \
      --app "$APPLICATION_INSIGHTS_NAME" \
      --analytics-query "$query" \
      -o json
  )"
  row="$(echo "$result" | jq -c '.tables[0].rows[0] // [0, 0, 0, 0, 0, 0]')"
  matched_count="$(echo "$row" | jq -r '.[0] // 0')"
  telemetry_rows="$(echo "$row" | jq -r '.[1] // 0')"
  trace_rows="$(echo "$row" | jq -r '.[2] // 0')"
  dependency_rows="$(echo "$row" | jq -r '.[3] // 0')"
  request_rows="$(echo "$row" | jq -r '.[4] // 0')"
  exception_rows="$(echo "$row" | jq -r '.[5] // 0')"
  status="waiting"
  if [[ "$telemetry_rows" -gt 0 && "$matched_count" -eq "${#conversation_ids[@]}" && "$exception_rows" -eq 0 ]]; then
    status="passed"
  fi

  jq -n \
    --arg status "$status" \
    --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg started_at "$started_at" \
    --arg application_insights_name "$APPLICATION_INSIGHTS_NAME" \
    --argjson conversation_ids "$conversation_ids_json" \
    --argjson matched_count "$matched_count" \
    --argjson telemetry_rows "$telemetry_rows" \
    --argjson trace_rows "$trace_rows" \
    --argjson dependency_rows "$dependency_rows" \
    --argjson request_rows "$request_rows" \
    --argjson exception_rows "$exception_rows" \
    '{
      status: $status,
      generated_at: $generated_at,
      e2e_started_at: $started_at,
      application_insights_name: $application_insights_name,
      conversation_ids: $conversation_ids,
      matched_conversation_count: $matched_count,
      telemetry_rows: $telemetry_rows,
      trace_rows: $trace_rows,
      dependency_rows: $dependency_rows,
      request_rows: $request_rows,
      exception_rows: $exception_rows
    }' >"$RESULT_FILE"

  if [[ "$status" == "passed" ]]; then
    echo "Application Insights telemetry check passed: ${telemetry_rows} correlated rows for ${matched_count} hosted E2E conversations."
    exit 0
  fi
  echo "Awaiting correlated telemetry (attempt ${attempt}/${MAX_ATTEMPTS}; rows=${telemetry_rows}, conversations=${matched_count}/${#conversation_ids[@]}, exceptions=${exception_rows})."
  sleep "$POLL_SECONDS"
done

jq '.status = "failed"' "$RESULT_FILE" >"${RESULT_FILE}.tmp"
mv "${RESULT_FILE}.tmp" "$RESULT_FILE"
echo "Application Insights telemetry was not correlated to all current hosted E2E conversations within the bounded wait."
exit 1
