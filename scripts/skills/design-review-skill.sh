#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

REPORT_FILE="backend/.foundry/results/report.json"
REPORT_BACKUP=".git/.design-review-report.backup.json"
restore_report=0

cleanup() {
  if [[ "$restore_report" -eq 1 && -f "$REPORT_BACKUP" ]]; then
    mv "$REPORT_BACKUP" "$REPORT_FILE"
  fi
}
trap cleanup EXIT

step() {
  echo
  echo "==> $1"
}

assert_contains() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if ! grep -Fq "$pattern" "$file"; then
    echo "[FAIL] Missing rubric/test requirement: $label"
    echo "  file: $file"
    echo "  expected text: $pattern"
    exit 1
  fi
}

step "Scope guard (avoid broad refactors)"
changed_files_count="$(git diff --name-only HEAD -- | wc -l | tr -d ' ')"
if [[ "$changed_files_count" -gt 20 ]]; then
  echo "[WARN] $changed_files_count files changed (review threshold: 20)."
  echo "Avoid broad refactors in this review skill unless explicitly required."
else
  echo "[PASS] Changed files: $changed_files_count"
fi

step "Backend formatting"
make format

step "Backend lint"
make lint

step "Backend tests"
make test-backend

step "Backend eval harness"
if [[ -f "$REPORT_FILE" ]]; then
  cp "$REPORT_FILE" "$REPORT_BACKUP"
  restore_report=1
fi

make eval-backend

if [[ "$restore_report" -eq 1 ]]; then
  mv "$REPORT_BACKUP" "$REPORT_FILE"
fi

step "Rubric validation"
RUBRIC_FILE="scripts/rubric/e2e-rubric.md"
E2E_SPEC_FILE="scripts/playwright/tests/workflow.e2e.spec.ts"

assert_contains "$RUBRIC_FILE" "Minimum 10/12 on automated runs." "rubric pass threshold"
assert_contains "$RUBRIC_FILE" "Any score 0 in criteria 1, 3, or 4 is automatic fail." "rubric critical fail clause"
assert_contains "$E2E_SPEC_FILE" "high-risk request triggers HITL and approve path completes" "happy + HITL approve flow"
assert_contains "$E2E_SPEC_FILE" "low-risk request completes without HITL" "happy no-HITL flow"
assert_contains "$E2E_SPEC_FILE" "reject decision escalates workflow" "exception/escalation flow"
assert_contains "$E2E_SPEC_FILE" "openStudioWithHealthyHistory" "Workflow History API health check"
assert_contains "$E2E_SPEC_FILE" "workflow history status filter loads JSON without fallback HTML" "Workflow History status-filter API health check"
assert_contains "$E2E_SPEC_FILE" "not valid JSON" "HTML-as-JSON UI regression guard"

echo "[PASS] Rubric and required flow coverage checks succeeded"

step "Playwright E2E"
if ! make test-e2e; then
  echo "[FAIL] E2E validation failed."
  echo "If this is an environment/runtime blocker, run:"
  echo "  make up && make test-e2e"
  echo "Or run containerized E2E:"
  echo "  make docker-test"
  exit 1
fi

echo "[PASS] E2E validation succeeded"

echo
echo "All design-review skill checks passed."
