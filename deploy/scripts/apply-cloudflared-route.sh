#!/usr/bin/env bash
# Add jobs.jbuschmann.com route to homelab-infra cloudflared config (thenetwork).
set -euo pipefail

HOMELAB_INFRA="${HOMELAB_INFRA:-$HOME/homelab-infra}"
CM="${HOMELAB_INFRA}/cluster/thenetwork/platform/cloudflared/configmap.yaml"
ROUTE='      - hostname: jobs.jbuschmann.com
        service: http://api.jobs-platform.svc.cluster.local:8000'

if [[ ! -f "${CM}" ]]; then
  echo "ERROR: ${CM} not found" >&2
  exit 1
fi

if grep -q 'jobs.jbuschmann.com' "${CM}"; then
  echo "Route already present in ${CM}"
else
  python3 - <<PY
from pathlib import Path
path = Path("${CM}")
text = path.read_text()
needle = "      - service: http_status:404"
if needle not in text:
    raise SystemExit("Could not find catch-all ingress block")
block = """${ROUTE}
"""
path.write_text(text.replace(needle, block + needle))
print("Added jobs.jbuschmann.com route")
PY
fi

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
kubectl apply -f "${CM}"
kubectl -n cloudflared rollout restart deployment/cloudflared
kubectl -n cloudflared rollout status deployment/cloudflared --timeout=120s
echo "Cloudflared updated. Test: curl -sf https://jobs.jbuschmann.com/health"
