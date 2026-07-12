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
new_conversation_id() {
  python3 - <<'PY'
import uuid
print(str(uuid.uuid4()))
PY
}

C1="$(new_conversation_id)"
HIGH_RISK="$(new_conversation_id)"

invoke_responses() {
  local conversation_id="$1"
  local message="$2"
  local raw
  raw="$(azd ai agent invoke order-resolution-hosted "$message" --protocol responses --conversation-id "$conversation_id" --output raw --no-prompt)"
  printf '%s\n' "$raw" | awk '
    found { print; next }
    /^\{/ {
      found = 1
      print
    }
  '
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

first_turn="$(invoke_responses "$C1" "Resolve delayed order ORD-1001")"
assert_json_field "$first_turn" '.thread_id == "'"$C1"'"'
assert_json_field "$first_turn" '.status == "completed"'
assert_json_field "$first_turn" '(.events // []) | map(.type) | index("tool.call") != null'
assert_json_field "$first_turn" '(.events // []) | map(.type) | index("workflow.output") != null'

second_turn="$(invoke_responses "$C1" "Why was that resolution selected?")"
assert_json_field "$second_turn" '.thread_id == "'"$C1"'"'
assert_json_field "$second_turn" '.status == "completed"'
assert_json_field "$second_turn" '.message | test("resolution was selected|Resolution complete"; "i")'

high_risk_start="$(invoke_responses "$HIGH_RISK" "Resolve delayed order ORD-1009")"
assert_json_field "$high_risk_start" '.status == "waiting_approval"'
assert_json_field "$high_risk_start" '(.events // []) | map(.type) | index("hitl.request") != null'

high_risk_resume="$(invoke_responses "$HIGH_RISK" "Approve")"
assert_json_field "$high_risk_resume" '.status == "completed"'
assert_json_field "$high_risk_resume" '(.events // []) | map(.type) | index("hitl.response") != null'
assert_json_field "$high_risk_resume" '(.events // []) | map(.type) | index("workflow.output") != null'

echo "Foundry Responses hosted E2E passed for conversations: ${C1}, ${HIGH_RISK} (base=${BASE_ID})"
