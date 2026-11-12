#!/usr/bin/env bash
# Validate a USAJOBS Search API key against data.usajobs.gov.
#
# Usage:
#   USAJOBS_API_KEY=... ./deploy/scripts/test-usajobs-api-key.sh
#   ./deploy/scripts/test-usajobs-api-key.sh   # reads deploy/secrets/.usajobs-api-key
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KEY_FILE="${REPO_ROOT}/deploy/secrets/.usajobs-api-key"
API_KEY="${USAJOBS_API_KEY:-}"
USER_AGENT="${USAJOBS_USER_AGENT:-you@example.com}"

if [[ -z "${API_KEY}" && -f "${KEY_FILE}" ]]; then
  API_KEY="$(tr -d '[:space:]' < "${KEY_FILE}")"
fi

if [[ -z "${API_KEY}" ]]; then
  echo "ERROR: set USAJOBS_API_KEY or create ${KEY_FILE}" >&2
  exit 1
fi

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

echo "=== Testing USAJOBS API key (user-agent: ${USER_AGENT}) ==="
kubectl exec -n jobs-platform deployment/worker -- python3 -c "
import httpx

api_key, user_agent = ${API_KEY@Q}, ${USER_AGENT@Q}
response = httpx.get(
    'https://data.usajobs.gov/api/search',
    params={'ResultsPerPage': 1, 'Page': 1},
    headers={
        'Host': 'data.usajobs.gov',
        'User-Agent': user_agent,
        'Authorization-Key': api_key,
    },
    timeout=30,
)
print(f'HTTP {response.status_code}')
if response.is_success:
    data = response.json()
    count = data.get('SearchResult', {}).get('SearchResultCount', 0)
    print(f'OK — search returned {count} result(s) on page 1')
else:
    print(response.text[:500])
    raise SystemExit(1)
"
