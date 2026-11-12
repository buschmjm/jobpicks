#!/usr/bin/env bash
# Build the Vite SPA with mobile env vars baked in for Capacitor.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export VITE_MOBILE_BUILD="${VITE_MOBILE_BUILD:-true}"
export VITE_APP_STOREFRONT="${VITE_APP_STOREFRONT:-US}"
export VITE_APP_BASE_URL="${VITE_APP_BASE_URL:-https://app.willowriverautomation.com/jobpicks}"
export VITE_APP_MOUNT_PATH="${VITE_APP_MOUNT_PATH:-/jobpicks}"

cd "${REPO_ROOT}/web"
npm ci --ignore-scripts 2>/dev/null || npm install
npm run build
echo "Mobile web build complete: ${REPO_ROOT}/web/dist"
