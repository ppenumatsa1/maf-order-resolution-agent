#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <owner/repo> <resource-group> <vm-name> [runner-labels]"
  exit 1
fi

REPO="$1"
RESOURCE_GROUP="$2"
VM_NAME="$3"
RUNNER_LABELS="${4:-foundry-private,linux,x64}"

TOKEN="$(gh api -X POST "repos/${REPO}/actions/runners/registration-token" --jq '.token')"

TMP_SETTINGS="$(mktemp)"
TMP_PROTECTED="$(mktemp)"
trap 'rm -f "$TMP_SETTINGS" "$TMP_PROTECTED"' EXIT

python3 - <<PY
import json
repo = "https://github.com/${REPO}"
token = """${TOKEN}"""
labels = """${RUNNER_LABELS}"""
command = f'''bash -lc '
set -euo pipefail
mkdir -p "$HOME/actions-runner"
cd "$HOME/actions-runner"
if [[ ! -f ./config.sh ]]; then
  curl -fsSL -o actions-runner.tar.gz https://github.com/actions/runner/releases/download/v2.327.1/actions-runner-linux-x64-2.327.1.tar.gz
  tar xzf actions-runner.tar.gz
fi
if [[ -f .runner ]]; then
  ./config.sh remove --token "{token}" || true
fi
./config.sh --unattended --url "{repo}" --token "{token}" --name "$(hostname)-foundry-private" --labels "{labels}" --work _work --replace
sudo ./svc.sh install "$USER" || true
sudo ./svc.sh start
sudo ./svc.sh status || true
'
'''

with open("${TMP_SETTINGS}", "w", encoding="utf-8") as f:
    json.dump({"fileUris": []}, f)
with open("${TMP_PROTECTED}", "w", encoding="utf-8") as f:
    json.dump({"commandToExecute": command}, f)
PY

az vm extension set \
  --resource-group "$RESOURCE_GROUP" \
  --vm-name "$VM_NAME" \
  --name customScript \
  --publisher Microsoft.Azure.Extensions \
  --version 2.1 \
  --settings "@${TMP_SETTINGS}" \
  --protected-settings "@${TMP_PROTECTED}" \
  --query provisioningState -o tsv

echo "Runner registration command submitted to VM extension."