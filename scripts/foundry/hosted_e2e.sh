#!/usr/bin/env bash
set -euo pipefail

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required binary: $1"
    exit 1
  }
}

require_bin azd
require_bin jq

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FOUNDRY_DIR="${FOUNDRY_DIR:-$ROOT_DIR/infra/foundry-hosted}"

if [[ ! -f "$FOUNDRY_DIR/azure.yaml" ]]; then
  echo "Unable to locate Foundry AZD project at $FOUNDRY_DIR"
  exit 1
fi

cd "$FOUNDRY_DIR"

BASE_ID="${1:-foundry-e2e-$(date +%s)}"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

extract_json_output() {
  local raw="${1:-}"
  local json_output=""
  json_output="$(printf '%s\n' "$raw" | sed -n 's/^\[order-resolution-hosted\][[:space:]]*//p' | tail -n 1)"
  if [[ -z "$json_output" ]]; then
    json_output="$(printf '%s\n' "$raw" | awk '
      found { print; next }
      /^\{/ {
        found = 1
        print
      }
    ')"
  fi
  printf '%s\n' "$json_output"
}

invoke_responses() {
  local conversation_id="${1:-}"
  local message="${2:-}"
  local mode="${3:-reuse}"
  local raw
  local rc
  for attempt in $(seq 1 20); do
    set +e
    if [[ -n "$conversation_id" ]]; then
      raw="$(azd ai agent invoke order-resolution-hosted "$message" --protocol responses --conversation-id "$conversation_id" --no-prompt 2>&1)"
    elif [[ "$mode" == "new" ]]; then
      raw="$(azd ai agent invoke order-resolution-hosted "$message" --protocol responses --new-conversation --new-session --no-prompt 2>&1)"
    else
      raw="$(azd ai agent invoke order-resolution-hosted "$message" --protocol responses --no-prompt 2>&1)"
    fi
    rc=$?
    set -e
    if [[ $rc -eq 0 ]] && echo "$raw" | grep -Eqi 'session_not_ready|424 Failed Dependency|\"code\"[[:space:]]*:[[:space:]]*\"session_not_ready\"'; then
      rc=1
    fi
    if [[ $rc -eq 0 ]]; then
      break
    fi
    if echo "$raw" | grep -Eqi 'HTTP (404|409|429|5[0-9]{2})'; then
      echo "Transient invoke failure (attempt $attempt/20, conversation_id=${conversation_id:-<new>}). Retrying..."
      sleep 15
      continue
    fi
    break
  done
  local json_output=""
  json_output="$(extract_json_output "$raw")"
  if [[ $rc -ne 0 && -n "$json_output" ]]; then
    echo "azd invoke returned rc=$rc with parseable JSON; continuing (conversation_id=${conversation_id:-<new>})." >&2
  elif [[ $rc -ne 0 ]]; then
    echo "azd invoke failed (rc=$rc, conversation_id=${conversation_id:-<new>}):" >&2
    echo "$raw" >&2
    exit $rc
  fi
  if [[ -z "$json_output" ]]; then
    echo "Unable to extract JSON payload from azd invoke output (conversation_id=${conversation_id:-<new>}):" >&2
    echo "$raw" >&2
    exit 1
  fi
  printf '%s\n' "$json_output"
}

invoke_responses_payload() {
  local conversation_id="${1:-}"
  local payload_json="${2:-}"
  local payload_file
  payload_file="$(mktemp)"
  printf '%s\n' "$payload_json" >"$payload_file"

  local raw
  local rc
  set +e
  if [[ -n "$conversation_id" ]]; then
    raw="$(azd ai agent invoke order-resolution-hosted --protocol responses --conversation-id "$conversation_id" --input-file "$payload_file" --no-prompt 2>&1)"
  else
    raw="$(azd ai agent invoke order-resolution-hosted --protocol responses --input-file "$payload_file" --no-prompt 2>&1)"
  fi
  rc=$?
  set -e
  local json_output=""
  json_output="$(extract_json_output "$raw")"
  if [[ $rc -ne 0 && -n "$json_output" ]]; then
    echo "azd payload invoke returned rc=$rc with parseable JSON; continuing (conversation_id=${conversation_id:-<new>})." >&2
  elif [[ $rc -ne 0 ]]; then
    rm -f "$payload_file"
    echo "azd payload invoke failed (rc=$rc, conversation_id=${conversation_id:-<new>}):" >&2
    echo "$raw" >&2
    exit $rc
  fi
  if [[ -z "$json_output" ]]; then
    rm -f "$payload_file"
    echo "Unable to extract JSON payload from azd payload invoke output (conversation_id=${conversation_id:-<new>}):" >&2
    echo "$raw" >&2
    exit 1
  fi
  rm -f "$payload_file"
  printf '%s\n' "$json_output"
}

extract_thread_id() {
  local json="$1"
  echo "$json" | jq -r '[.. | objects | (.thread_id? // .conversation_id? // empty)] | map(select(type=="string" and length>0)) | .[0] // empty'
}

assert_json_field() {
  local json="$1"
  local expr="$2"
  echo "$json" | jq -e "$expr" >/dev/null || {
    echo "Assertion failed: $expr"
    echo "$json"
    exit 1
  }
}

first_turn="$(invoke_responses "" "Resolve delayed order ORD-1001" "new")"
assert_json_field "$first_turn" '.status == "completed"'
assert_json_field "$first_turn" '(.events // []) | map(.type) | index("tool.call") != null'
assert_json_field "$first_turn" '(.events // []) | map(.type) | index("workflow.output") != null'
echo "Hosted smoke passed: low-risk order completed without HITL."
C1="$(extract_thread_id "$first_turn")"
if [[ -z "$C1" || "$C1" == "null" ]]; then
  echo "Missing thread_id in first responses turn"
  echo "$first_turn"
  exit 1
fi

second_turn="$(invoke_responses "$C1" "Why was that resolution selected?")"
SECOND_THREAD="$(extract_thread_id "$second_turn")"
if [[ "$SECOND_THREAD" != "$C1" ]]; then
  echo "Second turn did not preserve thread_id (expected=$C1 got=${SECOND_THREAD:-<empty>})"
  echo "$second_turn"
  exit 1
fi
assert_json_field "$second_turn" '.status == "completed"'
assert_json_field "$second_turn" '.message | test("resolution was selected|Resolution complete"; "i")'

high_risk_start="$(invoke_responses "" "Resolve delayed order ORD-1009" "new")"
assert_json_field "$high_risk_start" '.status == "waiting_approval"'
assert_json_field "$high_risk_start" '(.events // []) | map(.type) | index("hitl.request") != null'
HIGH_RISK="$(extract_thread_id "$high_risk_start")"
if [[ -z "$HIGH_RISK" || "$HIGH_RISK" == "null" ]]; then
  echo "Missing thread_id in high-risk responses turn"
  echo "$high_risk_start"
  exit 1
fi

HIGH_RISK_CHECKPOINT="$(echo "$high_risk_start" | jq -r '(.pending_approvals // [])[0].checkpoint_id // empty')"
if [[ -z "$HIGH_RISK_CHECKPOINT" ]]; then
  echo "Missing checkpoint_id in high-risk responses turn"
  echo "$high_risk_start"
  exit 1
fi
high_risk_resume_payload="$(jq -cn --arg input "Approve" --arg checkpoint "$HIGH_RISK_CHECKPOINT" '{input: $input, decision: "approve", checkpoint_id: $checkpoint}')"
high_risk_resume="$(invoke_responses_payload "$HIGH_RISK" "$high_risk_resume_payload")"
assert_json_field "$high_risk_resume" '.status == "completed"'
assert_json_field "$high_risk_resume" '(.events // []) | map(.type) | index("hitl.response") != null'
assert_json_field "$high_risk_resume" '(.events // []) | map(.type) | index("workflow.output") != null'

evidence_file="${FOUNDRY_E2E_EVIDENCE_FILE:-$ROOT_DIR/backend/.foundry/results/hosted-e2e-evidence.json}"
mkdir -p "$(dirname "$evidence_file")"
jq -n \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg started_at "$STARTED_AT" \
  --arg low_risk_thread_id "$C1" \
  --arg approved_thread_id "$HIGH_RISK" \
  --arg base_id "$BASE_ID" \
  '{generated_at: $generated_at, started_at: $started_at, base_id: $base_id, low_risk_thread_id: $low_risk_thread_id, approved_thread_id: $approved_thread_id}' \
  >"$evidence_file"

echo "Foundry Responses hosted E2E passed for conversations: ${C1}, ${HIGH_RISK} (base=${BASE_ID})"
