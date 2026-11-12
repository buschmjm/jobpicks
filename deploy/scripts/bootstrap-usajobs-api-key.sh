#!/usr/bin/env bash
# Apply USAJOBS Search API credentials to job-platform-secrets.
#
# USAJOBS is wired into the nightly ingest sweep (up to 5 pages / ~500 jobs per run)
# when USAJOBS_API_KEY is set. Request a free key at:
#   https://developer.usajobs.gov/apirequest/
# Use the same email for USAJOBS_USER_AGENT as on the request form.
#
# Usage:
#   USAJOBS_API_KEY=... USAJOBS_USER_AGENT=you@example.com \
#     ./deploy/scripts/bootstrap-usajobs-api-key.sh
#
# Optional: RUN_INGEST=1 to trigger a one-off ingest after applying secrets.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

KEY_FILE="${REPO_ROOT}/deploy/secrets/.usajobs-api-key"
API_KEY="${USAJOBS_API_KEY:-}"
USER_AGENT="${USAJOBS_USER_AGENT:-you@example.com}"

if [[ -z "${API_KEY}" && -f "${KEY_FILE}" ]]; then
  API_KEY="$(tr -d '[:space:]' < "${KEY_FILE}")"
fi

if [[ -z "${API_KEY}" ]]; then
  echo "ERROR: set USAJOBS_API_KEY or create ${KEY_FILE}" >&2
  echo "Request a free key: ./deploy/scripts/request-usajobs-api-key.sh" >&2
  exit 1
fi

if [[ "${SKIP_USAJOBS_TEST:-0}" != "1" ]]; then
  USAJOBS_API_KEY="${API_KEY}" USAJOBS_USER_AGENT="${USER_AGENT}" \
    "${REPO_ROOT}/deploy/scripts/test-usajobs-api-key.sh"
fi

echo "=== Applying USAJOBS credentials to job-platform-secrets ==="
USAJOBS_API_KEY="${API_KEY}" USAJOBS_USER_AGENT="${USER_AGENT}" \
  "${REPO_ROOT}/deploy/scripts/init-homelab-secrets.sh"

echo "=== Restarting api + worker to pick up secrets ==="
kubectl rollout restart deployment/api deployment/worker -n jobs-platform
kubectl rollout status deployment/api -n jobs-platform --timeout=180s
kubectl rollout status deployment/worker -n jobs-platform --timeout=180s

if [[ "${RUN_INGEST:-0}" == "1" ]]; then
  echo "=== Triggering one-off ingest job ==="
  kubectl create job "job-platform-ingest-manual-$(date +%s)" \
    --from=cronjob/ingest -n jobs-platform
fi

echo "USAJOBS credentials applied. Nightly ingest will pull federal jobs on the next cron run."
