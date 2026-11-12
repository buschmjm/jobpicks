#!/usr/bin/env bash
# Create or update job-platform-secrets on thenetwork from template + env.
#
# Usage:
#   JOBS_PLATFORM_DB_PASSWORD=... ./deploy/scripts/init-homelab-secrets.sh
#   JOBS_PLATFORM_DEV_DB_PASSWORD=... ./deploy/scripts/init-homelab-secrets.sh --env dev
#   # optional: ADZUNA_APP_ID, ADZUNA_APP_KEY, JSEARCH_API_KEY, SMTP_*
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

ENV="prod"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--env dev|prod]"
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
done

case "${ENV}" in
  dev)
    NAMESPACE="jobs-platform-dev"
    TEMPLATE="${REPO_ROOT}/deploy/secrets/job-platform-dev-secrets.secret.yaml.template"
    OUT="${REPO_ROOT}/deploy/secrets/job-platform-dev-secrets.secret.yaml"
    DB_PASS_VAR="JOBS_PLATFORM_DEV_DB_PASSWORD"
    ;;
  prod)
    NAMESPACE="jobs-platform"
    TEMPLATE="${REPO_ROOT}/deploy/secrets/job-platform-secrets.secret.yaml.template"
    OUT="${REPO_ROOT}/deploy/secrets/job-platform-secrets.secret.yaml"
    DB_PASS_VAR="JOBS_PLATFORM_DB_PASSWORD"
    ;;
  *)
    echo "ERROR: --env must be dev or prod" >&2
    exit 1
    ;;
esac

if [[ ! -f "${TEMPLATE}" ]]; then
  echo "ERROR: missing ${TEMPLATE}" >&2
  exit 1
fi

DB_PASS="${!DB_PASS_VAR:-}"
PASS_FILE="${REPO_ROOT}/deploy/secrets/.db-password"
if [[ "${ENV}" == "dev" ]]; then
  PASS_FILE="${REPO_ROOT}/deploy/secrets/.db-password-dev"
fi
if [[ -z "${DB_PASS}" && -f "${PASS_FILE}" ]]; then
  DB_PASS="$(cat "${PASS_FILE}")"
fi
if [[ -z "${DB_PASS}" ]]; then
  echo "ERROR: run bootstrap-database.sh --env ${ENV} first or set ${DB_PASS_VAR}" >&2
  exit 1
fi

# Re-runs (e.g. SMTP-only updates) must not rotate app secrets.
if [[ -z "${SECRET_KEY:-}" ]] && kubectl get secret job-platform-secrets -n "${NAMESPACE}" >/dev/null 2>&1; then
  SECRET_KEY="$(kubectl get secret job-platform-secrets -n "${NAMESPACE}" -o jsonpath='{.data.SECRET_KEY}' | base64 -d)"
  ADMIN_SECRET="$(kubectl get secret job-platform-secrets -n "${NAMESPACE}" -o jsonpath='{.data.ADMIN_SECRET}' | base64 -d)"
  INTERNAL_EVENTS_TOKEN="$(kubectl get secret job-platform-secrets -n "${NAMESPACE}" -o jsonpath='{.data.INTERNAL_EVENTS_TOKEN}' | base64 -d 2>/dev/null || true)"
fi
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
ADMIN_SECRET="${ADMIN_SECRET:-$(openssl rand -hex 24)}"
INTERNAL_EVENTS_TOKEN="${INTERNAL_EVENTS_TOKEN:-$(openssl rand -hex 24)}"

cp "${TEMPLATE}" "${OUT}"
sed -i "s|REPLACE_DB_PASSWORD|${DB_PASS}|g" "${OUT}"
sed -i "s|REPLACE_SECRET_KEY|${SECRET_KEY}|g" "${OUT}"
sed -i "s|REPLACE_ADMIN_SECRET|${ADMIN_SECRET}|g" "${OUT}"
sed -i "s|REPLACE_INTERNAL_EVENTS_TOKEN|${INTERNAL_EVENTS_TOKEN}|g" "${OUT}"

# Preserve optional fields from the live secret when not passed on the command line.
if kubectl get secret job-platform-secrets -n "${NAMESPACE}" >/dev/null 2>&1; then
  for key in ADZUNA_APP_ID ADZUNA_APP_KEY JSEARCH_API_KEY JSEARCH_ENABLED USAJOBS_API_KEY USAJOBS_USER_AGENT SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD EMAIL_FROM GOOGLE_MAPS_API_KEY INTERNAL_EVENTS_TOKEN; do
    if [[ -z "${!key:-}" ]]; then
      val="$(kubectl get secret job-platform-secrets -n "${NAMESPACE}" -o "jsonpath={.data.${key}}" 2>/dev/null | base64 -d 2>/dev/null || true)"
      if [[ -n "${val}" ]]; then
        printf -v "${key}" '%s' "${val}"
      fi
    fi
  done
fi

# Optional overrides from environment (or preserved values above)
python3 - "${OUT}" <<'PY'
import os
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
keys = [
    "ADZUNA_APP_ID",
    "ADZUNA_APP_KEY",
    "JSEARCH_API_KEY",
    "JSEARCH_ENABLED",
    "USAJOBS_API_KEY",
    "USAJOBS_USER_AGENT",
    "SMTP_HOST",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "EMAIL_FROM",
    "GOOGLE_MAPS_API_KEY",
]
for key in keys:
    val = os.environ.get(key, "")
    if not val:
        continue
    pattern = re.compile(rf"^  {re.escape(key)}:.*$", re.M)
    replacement = f'  {key}: "{val}"'
    if pattern.search(text):
        text = pattern.sub(replacement, text, count=1)
    else:
        text = text.rstrip() + "\n" + replacement + "\n"
port = os.environ.get("SMTP_PORT", "").strip()
if port:
    text = re.sub(r"^  SMTP_PORT:.*$", f'  SMTP_PORT: "{port}"', text, count=1, flags=re.M)
path.write_text(text)
PY

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
if [[ "${ENV}" == "prod" ]]; then
  kubectl apply -f "${REPO_ROOT}/deploy/k8s/base/namespace.yaml"
fi
kubectl apply -f "${OUT}"
echo "Applied secret job-platform-secrets in ${NAMESPACE} namespace."
echo "Local copy: ${OUT} (gitignored — do not commit)"
