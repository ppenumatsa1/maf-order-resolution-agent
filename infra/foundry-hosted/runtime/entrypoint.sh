#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEFAULT_ENV_FILE="$ROOT_DIR/infra/foundry-hosted/runtime/.env"
FALLBACK_ENV_FILE="$ROOT_DIR/infra/foundry-hosted/runtime/.env.example"
ENV_FILE="${1:-$DEFAULT_ENV_FILE}"

if [[ "$ENV_FILE" == "$DEFAULT_ENV_FILE" && ! -f "$ENV_FILE" && -f "$FALLBACK_ENV_FILE" ]]; then
  ENV_FILE="$FALLBACK_ENV_FILE"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$ROOT_DIR/backend"
if [[ ! -f ".venv/bin/activate" ]]; then
  echo "backend/.venv is missing. Run: make bootstrap" >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
