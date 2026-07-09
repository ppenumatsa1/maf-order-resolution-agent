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

BASE_THREAD_ID="${1:-foundry-e2e-$(date +%s)}"

invoke() {
  local payload="$1"
  local raw
  raw="$(azd ai agent invoke order-resolution-hosted "$payload" --protocol invocations --no-prompt)"
  # azd emits summary lines (and sometimes prefixes like "[agent] ") before JSON.
  # Keep only the JSON payload so jq-based assertions remain deterministic.
  printf '%s\n' "$raw" | awk '
    found { print; next }
    /\{/ {
      found = 1
      sub(/^[^{]*/, "")
      print
    }
  '
}

assert_has_event() {
  local json="$1"
  local event_type="$2"
  echo "$json" | jq -e --arg event_type "$event_type" '
    (.events // []) | map(.type) | index($event_type) != null
  ' >/dev/null || {
    echo "Expected event '$event_type' was not present"
    echo "$json"
    exit 1
  }
}

assert_not_event() {
  local json="$1"
  local event_type="$2"
  echo "$json" | jq -e --arg event_type "$event_type" '
    (.events // []) | map(.type) | index($event_type) == null
  ' >/dev/null || {
    echo "Unexpected event '$event_type' was present"
    echo "$json"
    exit 1
  }
}

low_thread="${BASE_THREAD_ID}-low"
high_thread="${BASE_THREAD_ID}-high"
damaged_thread="${BASE_THREAD_ID}-damaged"

low_result="$(invoke "{\"thread_id\":\"${low_thread}\",\"message\":\"ORD-1001 late delivery\"}")"
assert_has_event "$low_result" "workflow.stage"
assert_has_event "$low_result" "tool.call"
assert_has_event "$low_result" "workflow.output"
assert_not_event "$low_result" "hitl.request"

high_result="$(invoke "{\"thread_id\":\"${high_thread}\",\"message\":\"ORD-1009 delayed order telemetry gate ${high_thread}\"}")"
assert_has_event "$high_result" "workflow.stage"
assert_has_event "$high_result" "tool.call"
assert_has_event "$high_result" "checkpoint.created"
assert_has_event "$high_result" "hitl.request"
checkpoint_id="$(echo "$high_result" | jq -r '.. | objects | .checkpoint_id? // empty' | head -n1)"
if [[ -z "$checkpoint_id" || "$checkpoint_id" == "null" ]]; then
  echo "Missing checkpoint_id in high-risk HITL flow"
  echo "$high_result"
  exit 1
fi

resume_result="$(invoke "{\"operation\":\"resume_hitl\",\"thread_id\":\"${high_thread}\",\"checkpoint_id\":\"${checkpoint_id}\",\"decision\":\"approve\",\"reviewer\":\"github-runner\"}")"
assert_has_event "$resume_result" "hitl.response"
assert_has_event "$resume_result" "workflow.output"

damaged_result="$(invoke "{\"thread_id\":\"${damaged_thread}\",\"message\":\"My ORD-1001 item arrived damaged\"}")"
assert_has_event "$damaged_result" "checkpoint.created"
assert_has_event "$damaged_result" "hitl.request"

echo "Foundry hosted E2E passed for thread base: ${BASE_THREAD_ID}"
