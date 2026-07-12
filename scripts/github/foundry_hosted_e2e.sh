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

BASE_ID="${1:-foundry-e2e-$(date +%s)}"

invoke_responses() {
  local conversation_id="${1:-}"
  local message="${2:-}"
  local raw
  local rc
  set +e
  if [[ -n "$conversation_id" ]]; then
    raw="$(azd ai agent invoke order-resolution-hosted "$message" --protocol responses --conversation-id "$conversation_id" --output raw --no-prompt 2>&1)"
  else
    raw="$(azd ai agent invoke order-resolution-hosted "$message" --protocol responses --output raw --no-prompt 2>&1)"
  fi
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    echo "azd invoke failed (rc=$rc, conversation_id=${conversation_id:-<new>}):"
    echo "$raw"
    exit $rc
  fi
  printf '%s\n' "$raw" | awk '
    found { print; next }
    /^\{/ {
      found = 1
      print
    }
  '
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

first_turn="$(invoke_responses "" "Resolve delayed order ORD-1001")"
assert_json_field "$first_turn" '.status == "completed"'
assert_json_field "$first_turn" '(.events // []) | map(.type) | index("tool.call") != null'
assert_json_field "$first_turn" '(.events // []) | map(.type) | index("workflow.output") != null'
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

high_risk_start="$(invoke_responses "" "Resolve delayed order ORD-1009")"
assert_json_field "$high_risk_start" '.status == "waiting_approval"'
assert_json_field "$high_risk_start" '(.events // []) | map(.type) | index("hitl.request") != null'
HIGH_RISK="$(extract_thread_id "$high_risk_start")"
if [[ -z "$HIGH_RISK" || "$HIGH_RISK" == "null" ]]; then
  echo "Missing thread_id in high-risk responses turn"
  echo "$high_risk_start"
  exit 1
fi

high_risk_resume="$(invoke_responses "$HIGH_RISK" "Approve")"
assert_json_field "$high_risk_resume" '.status == "completed"'
assert_json_field "$high_risk_resume" '(.events // []) | map(.type) | index("hitl.response") != null'
assert_json_field "$high_risk_resume" '(.events // []) | map(.type) | index("workflow.output") != null'

echo "Foundry Responses hosted E2E passed for conversations: ${C1}, ${HIGH_RISK} (base=${BASE_ID})"
