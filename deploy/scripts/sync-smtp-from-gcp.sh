#!/usr/bin/env bash
# Pull existing SendGrid API key from GCP Secret Manager and apply SMTP settings
# to job-platform-secrets on thenetwork (or locally with --local).
#
# Uses the Metcalf SendGrid account (willowriverautomation@gmail.com). Sends as
# hello@willowriverautomation.com — domain already authenticated for WRA/Metcalf.
#
# Usage:
#   ./deploy/scripts/sync-smtp-from-gcp.sh              # SSH to homelab, apply, restart api
#   ./deploy/scripts/sync-smtp-from-gcp.sh --local      # kubectl on this machine
#
# Overrides:
#   GCP_PROJECT=metcalf-494223
#   GCP_SENDGRID_SECRET=SENDGRID_API_KEY
#   EMAIL_FROM='Willow River Automation <hello@willowriverautomation.com>'
#   HOMELAB_HOST=user@your-server
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GCP_PROJECT="${GCP_PROJECT:-metcalf-494223}"
GCP_SENDGRID_SECRET="${GCP_SENDGRID_SECRET:-SENDGRID_API_KEY}"
HOST="${HOMELAB_HOST:-user@your-server}"
DEST="${HOMELAB_DEST:-/home/dad/job-platform}"
EMAIL_FROM="${EMAIL_FROM:-Willow River Automation <hello@willowriverautomation.com>}"
LOCAL=false
if [[ "${1:-}" == "--local" ]]; then
  LOCAL=true
fi

echo "=== Fetching ${GCP_SENDGRID_SECRET} from GCP project ${GCP_PROJECT} ==="
API_KEY="$(gcloud secrets versions access latest --secret="${GCP_SENDGRID_SECRET}" --project="${GCP_PROJECT}")"
if [[ -z "${API_KEY}" ]]; then
  echo "ERROR: empty API key from ${GCP_PROJECT}/${GCP_SENDGRID_SECRET}" >&2
  exit 1
fi

apply_on_host() {
  export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
  SMTP_HOST=smtp.sendgrid.net \
  SMTP_PORT=587 \
  SMTP_USER=apikey \
  SMTP_PASSWORD="${API_KEY}" \
  EMAIL_FROM="${EMAIL_FROM}" \
  "${REPO_ROOT}/deploy/scripts/init-homelab-secrets.sh"
  kubectl rollout restart deployment/api deployment/worker -n jobs-platform
  kubectl rollout status deployment/api -n jobs-platform --timeout=120s
  echo "SMTP secrets applied; api/worker restarted."
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
# Pass SMTP vars safely; init script preserves existing SECRET_KEY/ADMIN_SECRET when re-run.
ssh "${SSH_OPTS[@]}" "${HOST}" \
  "export KUBECONFIG=\${KUBECONFIG:-\$HOME/.kube/config}; \
   SMTP_HOST=smtp.sendgrid.net SMTP_PORT=587 SMTP_USER=apikey \
   SMTP_PASSWORD=$(printf '%q' "${API_KEY}") \
   EMAIL_FROM=$(printf '%q' "${EMAIL_FROM}") \
   bash ${DEST}/deploy/scripts/init-homelab-secrets.sh && \
   kubectl rollout restart deployment/api deployment/worker -n jobs-platform && \
   kubectl rollout status deployment/api -n jobs-platform --timeout=120s"

echo "Done. Magic links will send from ${EMAIL_FROM} via SendGrid SMTP."
