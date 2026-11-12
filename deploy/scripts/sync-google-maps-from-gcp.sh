#!/usr/bin/env bash
# Pull GOOGLE_MAPS_API_KEY from GCP Secret Manager and apply to job-platform-secrets
# on thenetwork (or locally with --local).
#
# Usage:
#   ./deploy/scripts/sync-google-maps-from-gcp.sh              # SSH to homelab, apply, restart api
#   ./deploy/scripts/sync-google-maps-from-gcp.sh --local      # kubectl on this machine
#
# Overrides:
#   GCP_PROJECT=wr-automation-services
#   GCP_MAPS_SECRET=GOOGLE_MAPS_API_KEY
#   HOMELAB_HOST=user@your-server
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GCP_PROJECT="${GCP_PROJECT:-wr-automation-services}"
# Secret Manager lives in metcalf (billing enabled); API key is owned by wr-automation-services.
GCP_SECRET_PROJECT="${GCP_SECRET_PROJECT:-metcalf-494223}"
GCP_MAPS_SECRET="${GCP_MAPS_SECRET:-GOOGLE_MAPS_API_KEY}"
GCP_MAPS_KEY_NAME="${GCP_MAPS_KEY_NAME:-job-platform-browser}"
HOST="${HOMELAB_HOST:-user@your-server}"
DEST="${HOMELAB_DEST:-/home/dad/job-platform}"
LOCAL=false
if [[ "${1:-}" == "--local" ]]; then
  LOCAL=true
fi

echo "=== Fetching ${GCP_MAPS_SECRET} from GCP project ${GCP_SECRET_PROJECT} ==="
if gcloud secrets describe "${GCP_MAPS_SECRET}" --project="${GCP_SECRET_PROJECT}" >/dev/null 2>&1; then
  API_KEY="$(gcloud secrets versions access latest --secret="${GCP_MAPS_SECRET}" --project="${GCP_SECRET_PROJECT}")"
else
  echo "Secret not found; reading browser key from ${GCP_PROJECT} API Keys API"
  KEY_RESOURCE="$(gcloud services api-keys list \
    --project="${GCP_PROJECT}" \
    --filter="displayName:${GCP_MAPS_KEY_NAME}" \
    --format="value(name)" \
    --limit=1)"
  if [[ -z "${KEY_RESOURCE}" ]]; then
    echo "ERROR: no API key named ${GCP_MAPS_KEY_NAME} in ${GCP_PROJECT}" >&2
    exit 1
  fi
  API_KEY="$(gcloud services api-keys get-key-string "${KEY_RESOURCE}" --project="${GCP_PROJECT}" --format="value(keyString)")"
fi
if [[ -z "${API_KEY}" ]]; then
  echo "ERROR: empty API key from ${GCP_PROJECT}/${GCP_MAPS_SECRET}" >&2
  exit 1
fi

apply_on_host() {
  export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
  GOOGLE_MAPS_API_KEY="${API_KEY}" "${REPO_ROOT}/deploy/scripts/init-homelab-secrets.sh"
  kubectl rollout restart deployment/api -n jobs-platform
  kubectl rollout status deployment/api -n jobs-platform --timeout=120s
  echo "Google Maps API key applied; api restarted."
}

if [[ "${LOCAL}" == true ]]; then
  apply_on_host
  exit 0
fi

SSH_OPTS=(-F /dev/null -o PreferredAuthentications=password -o PubkeyAuthentication=no)
if [[ -z "${DISPLAY:-}" ]]; then
  export DISPLAY=:0
fi
if [[ -z "${SSH_ASKPASS:-}" ]] && [[ -x /usr/bin/ksshaskpass ]]; then
  export SSH_ASKPASS=/usr/bin/ksshaskpass
  export SSH_ASKPASS_REQUIRE=force
fi

echo "=== Applying on ${HOST}:${DEST} ==="
ssh "${SSH_OPTS[@]}" "${HOST}" \
  "export KUBECONFIG=\${KUBECONFIG:-\$HOME/.kube/config}; \
   GOOGLE_MAPS_API_KEY=$(printf '%q' "${API_KEY}") \
   bash ${DEST}/deploy/scripts/init-homelab-secrets.sh && \
   kubectl rollout restart deployment/api -n jobs-platform && \
   kubectl rollout status deployment/api -n jobs-platform --timeout=120s"

echo "Done. Address autocomplete is enabled at ${APP_BASE_URL:-https://jobs.jbuschmann.com}."
