#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

base_ref="${1:-HEAD}"
changed_files="$(git diff --name-only "$base_ref" --)"

if [[ -z "$changed_files" ]]; then
  echo "deploy_mode=app_only"
  echo "validation_mode=quick"
  echo "reason=no_changed_files"
  exit 0
fi

if grep -Eq '^(infra/|\.azure/|docker-compose\.yml|frontend/Dockerfile|frontend/nginx\.conf|backend/Dockerfile|\.github/workflows/)' <<<"$changed_files"; then
  echo "deploy_mode=full"
  echo "validation_mode=full"
  echo "reason=infra_or_runtime_surface_changed"
  exit 0
fi

if grep -Eq '^(backend/app/maf/|backend/app/api/v1/schemas/|backend/app/api/v1/routers/|backend/app/modules/order_resolution/|backend/evals/|backend/tests/test_workflow\.py|backend/evals/cases\.jsonl|docs/design/hitl-approval-conditions\.md)' <<<"$changed_files"; then
  echo "deploy_mode=app_only"
  echo "validation_mode=full"
  echo "reason=workflow_contract_or_hitl_surface_changed"
  exit 0
fi

echo "deploy_mode=app_only"
echo "validation_mode=quick"
echo "reason=application_only_change"
