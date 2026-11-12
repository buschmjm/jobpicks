#!/usr/bin/env bash
# One-time setup: enable Google Maps / Places APIs, create a browser-restricted API key,
# and store it in GCP Secret Manager for job-platform address autocomplete.
#
# Project: wr-automation-services (Willow River Automation). Override with GCP_PROJECT.
#
# Usage:
#   ./deploy/scripts/setup-google-maps-gcp.sh
#
# After setup, sync to homelab:
#   ./deploy/scripts/sync-google-maps-from-gcp.sh
set -euo pipefail

GCP_PROJECT="${GCP_PROJECT:-wr-automation-services}"
GCP_SECRET_PROJECT="${GCP_SECRET_PROJECT:-metcalf-494223}"
SECRET_NAME="${GCP_MAPS_SECRET:-GOOGLE_MAPS_API_KEY}"
KEY_DISPLAY_NAME="${GCP_MAPS_KEY_NAME:-job-platform-browser}"
APP_BASE_URL="${APP_BASE_URL:-https://jobs.jbuschmann.com}"

echo "=== Google Maps setup for project ${GCP_PROJECT} ==="
gcloud config set project "${GCP_PROJECT}"

BILLING_ENABLED="$(gcloud billing projects describe "${GCP_PROJECT}" --format='value(billingEnabled)' 2>/dev/null || true)"
if [[ "${BILLING_ENABLED}" != "True" && "${BILLING_ENABLED}" != "true" ]]; then
  echo "ERROR: Billing is not enabled on ${GCP_PROJECT}." >&2
  echo "Maps Platform returns InvalidKey / 'This page can't load Google Maps correctly' without billing." >&2
  echo "Link an open billing account, then re-run this script:" >&2
  echo "  gcloud billing projects link ${GCP_PROJECT} --billing-account=ACCOUNT_ID" >&2
  exit 1
fi

echo "=== Enabling Maps JavaScript API and Places API (New) ==="
# places.googleapis.com = Places API (New) — required for PlaceAutocompleteElement.
# Legacy google.maps.places.Autocomplete is unavailable to keys created after 2025-03-01.
gcloud services enable maps-backend.googleapis.com places.googleapis.com --project="${GCP_PROJECT}"

KEY_RESOURCE="$(gcloud services api-keys list \
  --project="${GCP_PROJECT}" \
  --filter="displayName:${KEY_DISPLAY_NAME}" \
  --format="value(name)" \
  --limit=1)"

if [[ -z "${KEY_RESOURCE}" ]]; then
  echo "=== Creating API key ${KEY_DISPLAY_NAME} ==="
  CREATE_OUTPUT="$(gcloud services api-keys create \
    --display-name="${KEY_DISPLAY_NAME}" \
    --project="${GCP_PROJECT}" \
    --format=json)"
  KEY_RESOURCE="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["name"])' "${CREATE_OUTPUT}")"
else
  echo "=== Reusing existing API key ${KEY_RESOURCE} ==="
fi

sleep 2

echo "=== Restricting key to Maps + Places and app referrers ==="
gcloud services api-keys update "${KEY_RESOURCE}" \
  --project="${GCP_PROJECT}" \
  --api-target=service=maps-backend.googleapis.com \
  --api-target=service=places.googleapis.com \
  --allowed-referrers="${APP_BASE_URL}/*,http://localhost:5173/*,http://127.0.0.1:5173/*"

API_KEY="$(gcloud services api-keys get-key-string "${KEY_RESOURCE}" --project="${GCP_PROJECT}" --format="value(keyString)")"
if [[ -z "${API_KEY}" ]]; then
  echo "ERROR: could not read API key string" >&2
  exit 1
fi

if gcloud secrets describe "${SECRET_NAME}" --project="${GCP_SECRET_PROJECT}" >/dev/null 2>&1; then
  echo "=== Adding new version to secret ${SECRET_NAME} in ${GCP_SECRET_PROJECT} ==="
  printf '%s' "${API_KEY}" | gcloud secrets versions add "${SECRET_NAME}" \
    --project="${GCP_SECRET_PROJECT}" \
    --data-file=-
else
  echo "=== Creating secret ${SECRET_NAME} in ${GCP_SECRET_PROJECT} ==="
  printf '%s' "${API_KEY}" | gcloud secrets create "${SECRET_NAME}" \
    --project="${GCP_SECRET_PROJECT}" \
    --replication-policy=automatic \
    --data-file=-
fi

echo ""
echo "Done."
echo "  Maps project:   ${GCP_PROJECT}"
echo "  Secret project: ${GCP_SECRET_PROJECT}"
echo "  Secret:         ${SECRET_NAME}"
echo "  Key:            ${KEY_RESOURCE}"
echo ""
echo "Next: ./deploy/scripts/sync-google-maps-from-gcp.sh"
