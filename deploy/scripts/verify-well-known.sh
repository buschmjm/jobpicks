#!/usr/bin/env bash
# Verify Universal/App Links files are publicly reachable (WS-8).
set -euo pipefail

BASE_URL="${APP_BASE_URL:-https://jobs.jbuschmann.com}"
BASE_URL="${BASE_URL%/}"
MOBILE_UA="${MOBILE_UA:-Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148}"

echo "Checking mobile public paths on $BASE_URL (UA: mobile Safari)"

curl -fsS -A "$MOBILE_UA" "$BASE_URL/.well-known/apple-app-site-association" | head -c 200
echo ""
curl -fsS -A "$MOBILE_UA" "$BASE_URL/.well-known/assetlinks.json"
echo ""

readiness="$(curl -fsS -A "$MOBILE_UA" "$BASE_URL/api/mobile/readiness")"
echo "$readiness"

if ! echo "$readiness" | grep -q '"apple_universal_links_configured"'; then
  echo "WARN: /api/mobile/readiness missing expected fields" >&2
  exit 1
fi

# Auth callback must not be blocked by edge bot rules (302 to Keycloak is OK; 403 challenge is not).
status="$(curl -s -o /dev/null -w "%{http_code}" -A "$MOBILE_UA" "$BASE_URL/auth/callback")"
if [[ "$status" == "403" ]]; then
  echo "FAIL: /auth/callback returned 403 for mobile UA — check Cloudflare bot rules" >&2
  exit 1
fi
echo "auth/callback HTTP $status (expected not 403)"

echo "well-known verification passed"
