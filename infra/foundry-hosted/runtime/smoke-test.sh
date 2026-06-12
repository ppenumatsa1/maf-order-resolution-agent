#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

curl --fail --silent "$BASE_URL/health" >/dev/null

HTTP_CODE="$(curl --silent --output /dev/null --write-out '%{http_code}' -X POST "$BASE_URL/api/chat/run" \
  -H 'Content-Type: application/json' \
  -d '{"thread_id":"smoke-foundry-hosted","message":"ORD-1009 delayed order"}')"

if [[ "$HTTP_CODE" == "200" ]]; then
  echo "Expected non-200 while hosted invocations endpoint is not wired, got: $HTTP_CODE" >&2
  exit 1
fi

echo "foundry-hosted smoke test passed (runtime wired and awaiting hosted endpoint)"
