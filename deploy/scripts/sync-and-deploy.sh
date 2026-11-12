#!/usr/bin/env bash
# Sync job-platform repo to thenetwork and run deploy.
#
# Usage from workstation:
#   make homelab-deploy
#   # or with DB password after bootstrap-database.sh on server:
#   JOBS_PLATFORM_DB_PASSWORD=... make homelab-deploy
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${HOMELAB_HOST:-user@your-server}"
DEST="${HOMELAB_DEST:-/home/dad/job-platform}"
SSH_OPTS=(-F /dev/null -o PreferredAuthentications=password -o PubkeyAuthentication=no)

echo "=== Verifying GitHub CI + image build ==="
"${REPO_ROOT}/deploy/scripts/verify-github-build.sh"

if [[ -z "${DISPLAY:-}" ]]; then
  export DISPLAY=:0
fi
if [[ -z "${SSH_ASKPASS:-}" ]] && [[ -x /usr/bin/ksshaskpass ]]; then
  export SSH_ASKPASS=/usr/bin/ksshaskpass
  export SSH_ASKPASS_REQUIRE=force
fi

echo "=== Syncing to ${HOST}:${DEST} ==="
rsync -az --delete \
  -e "ssh -F /dev/null" \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'node_modules' \
  --exclude 'web/dist' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  --exclude 'deploy/secrets/' \
  "${REPO_ROOT}/" "${HOST}:${DEST}/"

ssh "${SSH_OPTS[@]}" "${HOST}" "chmod +x ${DEST}/deploy/scripts/*.sh"

echo "=== Remote deploy ==="
ssh "${SSH_OPTS[@]}" "${HOST}" "bash -s" <<REMOTE
set -euo pipefail
cd ${DEST}
export KUBECONFIG=\${KUBECONFIG:-\$HOME/.kube/config}
if kubectl get secret job-platform-secrets -n jobs-platform >/dev/null 2>&1; then
  if [[ ! -f deploy/secrets/.db-password ]]; then
    mkdir -p deploy/secrets
    DATABASE_URL="\$(kubectl get secret job-platform-secrets -n jobs-platform -o jsonpath='{.data.DATABASE_URL}' | base64 -d)"
    python3 - "\$DATABASE_URL" <<'PY'
from pathlib import Path
from sys import argv
from urllib.parse import unquote, urlparse

raw = argv[1].replace("postgresql+psycopg", "postgresql", 1)
password = unquote(urlparse(raw).password or "")
Path("deploy/secrets/.db-password").write_text(password)
Path("deploy/secrets/.db-password").chmod(0o600)
PY
    echo "Restored deploy/secrets/.db-password from live k8s secret"
  fi
elif [[ ! -f deploy/secrets/.db-password ]]; then
  ./deploy/scripts/bootstrap-database.sh
fi
if ! kubectl get secret job-platform-secrets -n jobs-platform >/dev/null 2>&1; then
  ./deploy/scripts/init-homelab-secrets.sh
fi
./deploy/scripts/deploy-on-server.sh
REMOTE

echo "Done. Configure cloudflared route if not yet applied (deploy/homelab-infra/README.md)."
