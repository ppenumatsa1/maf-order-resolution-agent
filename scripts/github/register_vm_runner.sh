#!/usr/bin/env bash
set -euo pipefail

# Idempotent bootstrap for a self-hosted GitHub Actions runner on a private VM.
# Requires:
#   - GH_RUNNER_PAT with repo admin/workflow scope
#   - REPO in owner/name form
# Optional:
#   - RUNNER_VERSION (default: 2.328.0)
#   - RUNNER_LABEL (default: foundry-private)
#   - RUNNER_NAME_PREFIX (default: vm-${HOSTNAME})
#   - RUNNER_WORKDIR (default: /mnt/actions-runner)
#   - SKIP_VM_BOOTSTRAP=1 to skip package/tool bootstrap

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required binary: $1"
    exit 1
  }
}

require_bin curl
require_bin jq
require_bin tar
require_bin sudo

: "${GH_RUNNER_PAT:?GH_RUNNER_PAT is required}"
: "${REPO:?REPO is required (owner/repo)}"

RUNNER_VERSION="${RUNNER_VERSION:-2.328.0}"
RUNNER_LABEL="${RUNNER_LABEL:-foundry-private}"
RUNNER_WORKDIR="${RUNNER_WORKDIR:-/mnt/actions-runner}"
RUNNER_HOME="${RUNNER_HOME:-$RUNNER_WORKDIR/home}"
RUNNER_NAME_PREFIX="${RUNNER_NAME_PREFIX:-vm-$(hostname)}"
RUNNER_NAME="${RUNNER_NAME:-${RUNNER_NAME_PREFIX}-${RUNNER_LABEL}}"
RUNNER_USER="${RUNNER_USER:-${SUDO_USER:-$USER}}"
RUNNER_DIR="$RUNNER_WORKDIR/$RUNNER_NAME"
REPO_URL="https://github.com/$REPO"

if [[ "${SKIP_VM_BOOTSTRAP:-0}" != "1" ]]; then
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  "${script_dir}/bootstrap_vm_runner_host.sh"
fi

for required_cmd in git docker az azd; do
  require_bin "$required_cmd"
done

if ! sudo docker info >/dev/null 2>&1; then
  echo "Docker daemon is not available. Start docker and retry."
  exit 1
fi

mkdir -p "$RUNNER_DIR" "$RUNNER_HOME"
cd "$RUNNER_DIR"

mkdir -p /mnt/.azure /mnt/.azd /mnt/.tmp
grep -q 'AZURE_CONFIG_DIR=/mnt/.azure' /etc/environment 2>/dev/null || echo 'AZURE_CONFIG_DIR=/mnt/.azure' | sudo tee -a /etc/environment >/dev/null
grep -q 'AZD_CONFIG_DIR=/mnt/.azd' /etc/environment 2>/dev/null || echo 'AZD_CONFIG_DIR=/mnt/.azd' | sudo tee -a /etc/environment >/dev/null
grep -q 'TMPDIR=/mnt/.tmp' /etc/environment 2>/dev/null || echo 'TMPDIR=/mnt/.tmp' | sudo tee -a /etc/environment >/dev/null
grep -q "HOME=$RUNNER_HOME" /etc/environment 2>/dev/null || echo "HOME=$RUNNER_HOME" | sudo tee -a /etc/environment >/dev/null

if [[ ! -x ./config.sh ]]; then
  archive="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
  url="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${archive}"
  echo "Downloading runner ${RUNNER_VERSION}"
  curl -fsSL "$url" -o "$archive"
  tar xzf "$archive"
  rm -f "$archive"
fi

token="$(
  curl -fsSL -X POST \
    -H "Authorization: token ${GH_RUNNER_PAT}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPO}/actions/runners/registration-token" | jq -r '.token'
)"
if [[ -z "$token" || "$token" == "null" ]]; then
  echo "Failed to fetch registration token for $REPO"
  exit 1
fi

if [[ -f .runner ]]; then
  echo "Runner already configured; refreshing service."
else
  ./config.sh \
    --url "$REPO_URL" \
    --token "$token" \
    --name "$RUNNER_NAME" \
    --labels "self-hosted,${RUNNER_LABEL}" \
    --work "_work" \
    --unattended \
    --replace
fi

if sudo ./svc.sh status 2>/dev/null | grep -Eq 'active|running'; then
  echo "Runner service already active; restarting."
  sudo ./svc.sh stop || true
fi
sudo ./svc.sh install "$RUNNER_USER" || true
sudo ./svc.sh start
sudo ./svc.sh status | cat

echo "Runner registration complete for $REPO as $RUNNER_NAME with label $RUNNER_LABEL."
