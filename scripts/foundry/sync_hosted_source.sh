#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="${ROOT_DIR}/backend"
DST_DIR="${ROOT_DIR}/infra/foundry-hosted/agent"

if [[ ! -f "${SRC_DIR}/agent.yaml" || ! -f "${SRC_DIR}/foundry/main.py" ]]; then
  echo "Hosted source validation failed: backend/agent.yaml and backend/foundry/main.py are required."
  exit 1
fi

rm -rf "${DST_DIR}"
mkdir -p "${DST_DIR}"
cp -a "${SRC_DIR}/." "${DST_DIR}/"
rm -rf "${DST_DIR}/.venv" "${DST_DIR}/tests" "${DST_DIR}/.pytest_cache"
