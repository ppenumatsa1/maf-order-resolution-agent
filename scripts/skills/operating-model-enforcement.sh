#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

base_ref="${1:-HEAD}"
changed_files="$(git diff --name-only "$base_ref" --)"

if [[ -z "$changed_files" ]]; then
  echo "[PASS] operating-model: no changed files"
  exit 0
fi

require_changed() {
  local required_file="$1"
  local reason="$2"
  if ! grep -Fxq "$required_file" <<<"$changed_files"; then
    echo "[FAIL] operating-model: missing required update '$required_file' ($reason)"
    exit 1
  fi
}

if grep -Eq '^(backend/app/maf/executors/hitl\.py|backend/app/modules/order_resolution/hitl\.py|backend/app/maf/workflows/order_resolution\.py)$' <<<"$changed_files"; then
  require_changed "docs/design/hitl-approval-conditions.md" "HITL decision logic changed"
  if ! grep -Eq '^(backend/tests/test_workflow\.py|backend/.foundry/datasets/order-resolution-hosted-cases\.jsonl)$' <<<"$changed_files"; then
    echo "[FAIL] operating-model: HITL changes require workflow tests or hosted eval dataset updates"
    exit 1
  fi
fi

if grep -Eq '^(infra/azure-apphosted/|azure\.yaml|scripts/azure/)' <<<"$changed_files"; then
  require_changed "docs/design/issues-changes-fixes.md" "App-hosted deployment surfaces changed"
fi

echo "[PASS] operating-model enforcement checks"
