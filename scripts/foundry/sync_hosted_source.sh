#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_DIR="${ROOT_DIR}/backend"
TARGET_DIR="${ROOT_DIR}/infra/foundry-hosted/agent"

if [[ ! -f "${SOURCE_DIR}/agent.yaml" || ! -f "${SOURCE_DIR}/foundry/main.py" ]]; then
  echo "backend/agent.yaml and backend/foundry/main.py are required."
  exit 1
fi

rm -rf "${TARGET_DIR}"
mkdir -p "${TARGET_DIR}"
tar --exclude='.env' --exclude='.venv' --exclude='tests' --exclude='.pytest_cache' --exclude='__pycache__' \
  --exclude='.foundry/results' --exclude='tmp-foundry-sample' \
  -C "${SOURCE_DIR}" -cf - . | tar -C "${TARGET_DIR}" -xf -
