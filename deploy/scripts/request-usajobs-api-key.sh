#!/usr/bin/env bash
# Submit a USAJOBS Search API key request from the jobs-platform worker pod.
#
# USAJOBS emails the Authorization-Key to the address you provide. Use the same
# email for USAJOBS_USER_AGENT when bootstrapping.
#
# Usage:
#   ./deploy/scripts/request-usajobs-api-key.sh
#   GIVEN_NAME=Ada LAST_NAME=Lovelace EMAIL=you@example.com ./deploy/scripts/request-usajobs-api-key.sh
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

GIVEN_NAME="${GIVEN_NAME:-}"
LAST_NAME="${LAST_NAME:-}"
EMAIL="${EMAIL:-you@example.com}"
PHONE="${PHONE:-0000000000}"
COMPANY="${COMPANY:-Willow River Automation}"
REASON="${REASON:-Personal job search platform ingesting public federal job listings for matching and alerts.}"

echo "=== Requesting USAJOBS API key for ${EMAIL} from worker pod ==="
kubectl exec -n jobs-platform deployment/worker -- python3 -c "
import json
import httpx

given, last, email, phone, company, reason = ${GIVEN_NAME@Q}, ${LAST_NAME@Q}, ${EMAIL@Q}, ${PHONE@Q}, ${COMPANY@Q}, ${REASON@Q}
client = httpx.Client(timeout=30)
cfg = client.get('https://developer.usajobs.gov/Client/GetClientConfigAsJson')
cfg.raise_for_status()
data_home = json.loads(cfg.json()['value']).get('DataHome') or 'https://data.usajobs.gov/'
endpoint = f\"{data_home}api/developer/InsertAPIRequest\"
payload = {
    'givenName': given,
    'lastName': last,
    'emailAddress': email,
    'phoneNumber': phone,
    'companyAgency': company,
    'requestReason': reason,
    'agreeCheck': 'true',
}
response = client.post(
    endpoint,
    data=payload,
    headers={'Content-Type': 'application/x-www-form-urlencoded'},
)
redirect = response.headers.get('hx-redirect', '')
print(f'HTTP {response.status_code}', end='')
if redirect:
    print(f' ({redirect})')
else:
    print()
if redirect == 'AddRequestExists':
    print(
        'A key was already requested for this email. Check your inbox for a USAJOBS '
        'developer email, or contact vendor-help@usajobs.gov to reissue.'
    )
elif response.is_success:
    print('Request submitted. Check your email for the Authorization-Key.')
else:
    print('Request failed. Try https://developer.usajobs.gov/apirequest/ in a browser.')
    raise SystemExit(1)
"

echo "After you have the key:"
echo "  USAJOBS_API_KEY=... RUN_INGEST=1 ./deploy/scripts/bootstrap-usajobs-api-key.sh"
