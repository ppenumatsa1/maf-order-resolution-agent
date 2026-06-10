#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

curl --fail --silent "$BASE_URL/health" >/dev/null

RUN_RESPONSE="$(curl --silent --show-error -X POST "$BASE_URL/api/chat/run" \
  -H 'Content-Type: application/json' \
  -d '{"thread_id":"smoke-apphosted-ord1001","message":"ORD-1001 late delivery"}')"

python3 - <<'PY' "$RUN_RESPONSE" "$BASE_URL"
import json
import sys
import urllib.request

payload = json.loads(sys.argv[1])
base_url = sys.argv[2]
thread_id = payload.get("thread_id")
if not thread_id:
    raise SystemExit("thread_id missing in /api/chat/run response")

with urllib.request.urlopen(f"{base_url}/api/workflows/{thread_id}/events?limit=200") as response:
    events_payload = json.loads(response.read().decode("utf-8"))

types = [item.get("type") for item in events_payload.get("items", [])]
if "workflow.output" not in types:
    raise SystemExit("workflow.output not emitted")
if "hitl.request" in types:
    raise SystemExit("unexpected hitl.request for low-risk ORD-1001 flow")
print("azure-apphosted smoke test passed")
PY
