#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT_DIR"
if [[ ! -f ".venv/bin/activate" ]]; then
  echo "backend/.venv is missing. Run: make bootstrap" >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
