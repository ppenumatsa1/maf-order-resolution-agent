#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
THREAD_ID="${2:-smoke-foundry-hosted}"

curl --fail --silent "$BASE_URL/health" >/dev/null

response_json="$(
curl --fail --silent -X POST "$BASE_URL/api/chat/run" \
  -H 'Content-Type: application/json' \
  -d "{\"thread_id\":\"${THREAD_ID}\",\"message\":\"ORD-1009 delayed order\"}"
)"

echo "$response_json" | grep -q 'checkpoint.created'
echo "$response_json" | grep -q 'hitl.request'

echo "foundry-hosted smoke test passed (HITL event path verified)"
