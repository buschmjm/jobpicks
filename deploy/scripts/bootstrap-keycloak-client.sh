#!/usr/bin/env bash
# Register the job-platform public OIDC client in the homelab Keycloak realm.
#
# Run on thenetwork:
#   ./deploy/scripts/bootstrap-keycloak-client.sh
set -euo pipefail

HOMELAB_INFRA="${HOMELAB_INFRA:-$HOME/homelab-infra}"
SECRETS="${HOMELAB_INFRA}/cluster/thenetwork/apps/keycloak/values.secrets.yaml"
APP_BASE_URL="${APP_BASE_URL:-https://app.willowriverautomation.com/jobpicks}"
APP_ALT_BASE_URLS="${APP_ALT_BASE_URLS:-https://jobs.jbuschmann.com}"
APP_MOUNT_PATH="${APP_MOUNT_PATH:-/jobpicks}"
REALM="${KEYCLOAK_REALM:-homelab}"
CLIENT_ID="${KEYCLOAK_CLIENT_ID:-job-platform}"
KC="http://127.0.0.1:18080"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

if [[ ! -f "${SECRETS}" ]]; then
  echo "ERROR: missing ${SECRETS}" >&2
  exit 1
fi

ADMIN_PW="$(python3 -c "import yaml; from pathlib import Path; print(yaml.safe_load(Path('${SECRETS}').read_text())['auth']['adminPassword'])")"

echo "=== Port-forward Keycloak admin API ==="
kubectl port-forward -n keycloak svc/keycloak 18080:80 >/tmp/kc-pf.log 2>&1 &
PF_PID=$!
trap 'kill ${PF_PID} 2>/dev/null || true' EXIT
sleep 2

echo "=== Obtaining admin token ==="
TOKEN="$(curl -sf -X POST "${KC}/realms/master/protocol/openid-connect/token" \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=${ADMIN_PW}" \
  -d "grant_type=password" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")"

CLIENT_JSON="$(mktemp)"
REALM_JSON="$(mktemp)"
trap 'rm -f "${CLIENT_JSON}" "${REALM_JSON}"; kill ${PF_PID} 2>/dev/null || true' EXIT

export CLIENT_ID APP_BASE_URL APP_ALT_BASE_URLS APP_MOUNT_PATH REALM
EXISTING_ID="$(curl -sf -H "Authorization: Bearer ${TOKEN}" \
  "${KC}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['id'] if d else '')")"

if [[ -n "${EXISTING_ID}" ]]; then
  echo "Updating client ${CLIENT_ID} (${EXISTING_ID})"
  curl -sf -H "Authorization: Bearer ${TOKEN}" \
    "${KC}/admin/realms/${REALM}/clients/${EXISTING_ID}" > "${CLIENT_JSON}"
  python3 - <<'PY' "${CLIENT_JSON}"
import json, os, sys
from pathlib import Path
from urllib.parse import urlparse

path = Path(sys.argv[1])
client = json.loads(path.read_text())
redirects = set(client.get("redirectUris") or [])
origins = set(client.get("webOrigins") or [])

mount = os.environ.get("APP_MOUNT_PATH", "").strip().rstrip("/")

def public_root(base: str) -> str:
    root = base.strip().rstrip("/")
    if not root:
        return ""
    if mount and not root.endswith(mount):
        root = f"{root}{mount}"
    return root

def web_origin(base: str) -> str:
    parsed = urlparse(public_root(base))
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"

raw_bases = [os.environ.get("APP_BASE_URL", "")]
raw_bases.extend(p.strip() for p in os.environ.get("APP_ALT_BASE_URLS", "").split(",") if p.strip())

public_roots: list[str] = []
for raw in raw_bases:
    root = public_root(raw)
    if root:
        public_roots.append(root)
        redirects.update([f"{root}/auth/callback", f"{root}/*"])
        origin = web_origin(raw)
        if origin:
            origins.add(origin)

logout_bases = " ".join(f"{root}/*" for root in public_roots)
client.update({
    "clientId": os.environ["CLIENT_ID"],
    "name": "JobPicks",
    "description": "AI job discovery — swipe deck, advisor, and resume tools",
    "enabled": True,
    "publicClient": True,
    "standardFlowEnabled": True,
    "directAccessGrantsEnabled": False,
    "implicitFlowEnabled": False,
    "serviceAccountsEnabled": False,
    "redirectUris": sorted(redirects),
    "webOrigins": sorted(origins),
    "attributes": {
        **(client.get("attributes") or {}),
        "post.logout.redirect.uris": logout_bases or (os.environ["APP_BASE_URL"] + "/*"),
        "pkce.code.challenge.method": "S256",
    },
    "defaultClientScopes": sorted(set((client.get("defaultClientScopes") or []) + [
        "web-origins", "acr", "profile", "roles", "basic", "email",
    ])),
})
path.write_text(json.dumps(client))
PY
  curl -sf -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    --data-binary @"${CLIENT_JSON}" \
    "${KC}/admin/realms/${REALM}/clients/${EXISTING_ID}" >/dev/null
else
  echo "Creating client ${CLIENT_ID}"
  python3 - <<'PY' > "${CLIENT_JSON}"
import json, os
print(json.dumps({
  "clientId": os.environ["CLIENT_ID"],
  "name": "JobPicks",
  "description": "AI job discovery — swipe deck + apply to-do",
  "enabled": True,
  "publicClient": True,
  "standardFlowEnabled": True,
  "directAccessGrantsEnabled": False,
  "implicitFlowEnabled": False,
  "serviceAccountsEnabled": False,
  "redirectUris": [
    os.environ["APP_BASE_URL"] + "/auth/callback",
    os.environ["APP_BASE_URL"] + "/*",
  ],
  "webOrigins": [os.environ["APP_BASE_URL"]],
  "attributes": {
    "post.logout.redirect.uris": os.environ["APP_BASE_URL"] + "/*",
    "pkce.code.challenge.method": "S256",
  },
  "defaultClientScopes": ["web-origins", "acr", "profile", "roles", "basic", "email"],
}))
PY
  curl -sf -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    --data-binary @"${CLIENT_JSON}" \
    "${KC}/admin/realms/${REALM}/clients" >/dev/null
fi

echo "Done. Authority: https://auth.jbuschmann.com/realms/${REALM}"
echo "Client ID: ${CLIENT_ID}"
