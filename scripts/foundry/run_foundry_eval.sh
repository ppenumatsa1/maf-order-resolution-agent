#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FOUNDRY_AZD_DIR="${FOUNDRY_AZD_DIR:-$ROOT_DIR/infra/foundry-hosted}"
FOUNDRY_AZD_ENV_NAME="${FOUNDRY_AZD_ENV_NAME:-}"

usage() {
  echo "Usage: $0 [--check]" >&2
}

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--check" ) ]]; then
  usage
  exit 2
fi

command -v azd >/dev/null 2>&1 || {
  echo "Missing required binary: azd" >&2
  exit 1
}

if [[ ! -f "$FOUNDRY_AZD_DIR/azure.yaml" ]]; then
  echo "Unable to locate Foundry AZD project at $FOUNDRY_AZD_DIR" >&2
  exit 1
fi

azd_args=(env get-value --cwd "$FOUNDRY_AZD_DIR" --no-prompt)
if [[ -n "$FOUNDRY_AZD_ENV_NAME" ]]; then
  azd_args+=(--environment "$FOUNDRY_AZD_ENV_NAME")
fi

read_azd_value() {
  local key="$1"
  local value
  if ! value="$(azd "${azd_args[@]}" "$key" 2>/dev/null)"; then
    echo "Unable to read $key from the selected Foundry AZD environment." >&2
    exit 1
  fi
  printf '%s' "$value"
}

export_required_azd_value() {
  local key="$1"
  local value
  value="$(read_azd_value "$key")"
  if [[ -z "$value" ]]; then
    echo "Missing required Foundry AZD environment value: $key" >&2
    exit 1
  fi
  export "$key=$value"
}

# Read only the evaluator's non-secret configuration. Do not source azd .env files
# or print values, since those files can contain unrelated credentials.
export_required_azd_value FOUNDRY_PROJECTS_ENDPOINT
export_required_azd_value FOUNDRY_MODEL_DEPLOYMENT_NAME

judge_model="$(azd "${azd_args[@]}" FOUNDRY_EVAL_MODEL 2>/dev/null || true)"
if [[ -n "$judge_model" ]]; then
  export FOUNDRY_EVAL_MODEL="$judge_model"
fi

if [[ "${1:-}" == "--check" ]]; then
  if [[ -n "$FOUNDRY_AZD_ENV_NAME" ]]; then
    echo "Foundry evaluation configuration loaded from AZD environment: $FOUNDRY_AZD_ENV_NAME"
  else
    echo "Foundry evaluation configuration loaded from the selected AZD environment."
  fi
  exit 0
fi

cd "$ROOT_DIR/backend"
exec "$ROOT_DIR/backend/.venv/bin/python" -m evals.foundry_eval_runner
