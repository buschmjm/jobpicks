#!/usr/bin/env bash
# Full deploy on thenetwork: build image, import to k3s, apply manifests, migrate.
#
# Prerequisites:
#   - docker, kubectl, ~/.kube/config
#   - secrets applied in target namespace (init-homelab-secrets.sh)
#
# Usage:
#   ./deploy/scripts/deploy-on-server.sh              # prod (jobs-platform)
#   ./deploy/scripts/deploy-on-server.sh --env dev  # dev (jobs-platform-dev)
#   ./deploy/scripts/deploy-on-server.sh --env prod --tag abc123def456
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

ENV="prod"
TAG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENV="$2"
      shift 2
      ;;
    --tag)
      TAG="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--env dev|prod] [--tag IMAGE_TAG]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

case "${ENV}" in
  dev)
    NAMESPACE="jobs-platform-dev"
    OVERLAY="${REPO_ROOT}/deploy/k8s/overlays/dev"
    IMAGE_TAG="${TAG:-dev}"
    HEALTH_URL="https://jobs-dev.jbuschmann.com/health"
    SECRETS_FILE="${REPO_ROOT}/deploy/secrets/job-platform-dev-secrets.secret.yaml"
    ;;
  prod)
    NAMESPACE="jobs-platform"
    OVERLAY="${REPO_ROOT}/deploy/k8s/overlays/homelab"
    IMAGE_TAG="${TAG:-latest}"
    HEALTH_URL="https://app.willowriverautomation.com/health"
    SECRETS_FILE="${REPO_ROOT}/deploy/secrets/job-platform-secrets.secret.yaml"
    ;;
  *)
    echo "ERROR: --env must be dev or prod (got ${ENV})" >&2
    exit 1
    ;;
esac

IMAGE="job-platform:${IMAGE_TAG}"
cd "${REPO_ROOT}"

echo "=== Deploying ${ENV} (${NAMESPACE}) image ${IMAGE} ==="
docker build -t "${IMAGE}" .
# Prod keeps :latest alias for rollouts that reference latest.
if [[ "${ENV}" == "prod" && "${IMAGE_TAG}" != "latest" ]]; then
  docker tag "${IMAGE}" "job-platform:latest"
fi
if [[ "${ENV}" == "dev" && "${IMAGE_TAG}" != "dev" ]]; then
  docker tag "${IMAGE}" "job-platform:dev"
fi

echo "=== Applying namespace + secrets check ==="
if ! kubectl get secret job-platform-secrets -n "${NAMESPACE}" >/dev/null 2>&1; then
  if [[ -f "${SECRETS_FILE}" ]]; then
    kubectl apply -f "${SECRETS_FILE}"
  else
    echo "ERROR: job-platform-secrets not found in ${NAMESPACE}." >&2
    echo "Run: ./deploy/scripts/init-homelab-secrets.sh --env ${ENV}" >&2
    exit 1
  fi
fi

kubectl delete job job-platform-import-image -n "${NAMESPACE}" --ignore-not-found
kubectl delete job job-platform-migrate -n "${NAMESPACE}" --ignore-not-found

echo "=== Applying k8s manifests ==="
kubectl apply -k "${OVERLAY}"

echo "=== Importing image into k3s ==="
kubectl delete job job-platform-import-image -n "${NAMESPACE}" --ignore-not-found
kubectl apply -f "${OVERLAY}/import-images-job.yaml"
# Patch import job image env if using custom tag
if [[ "${IMAGE_TAG}" != "dev" && "${IMAGE_TAG}" != "latest" ]]; then
  kubectl set env job/job-platform-import-image -n "${NAMESPACE}" IMAGE="${IMAGE}" || true
fi
kubectl wait --for=condition=complete job/job-platform-import-image -n "${NAMESPACE}" --timeout=300s
kubectl logs -n "${NAMESPACE}" job/job-platform-import-image

echo "=== Running database migrations ==="
kubectl delete job job-platform-migrate -n "${NAMESPACE}" --ignore-not-found
sed "s/namespace: jobs-platform/namespace: ${NAMESPACE}/" \
  "${REPO_ROOT}/deploy/k8s/base/migrate-job.yaml" | kubectl apply -f -
if kubectl wait --for=condition=complete job/job-platform-migrate -n "${NAMESPACE}" --timeout=120s; then
  kubectl logs -n "${NAMESPACE}" job/job-platform-migrate
else
  echo "WARNING: migrate did not finish in 120s; dumping logs and continuing."
  kubectl logs -n "${NAMESPACE}" -l job-name=job-platform-migrate --tail=80 || true
fi

echo "=== Rolling out api + worker ==="
kubectl rollout restart deployment/api deployment/worker -n "${NAMESPACE}"
kubectl rollout status deployment/api -n "${NAMESPACE}" --timeout=180s
kubectl rollout status deployment/worker -n "${NAMESPACE}" --timeout=180s

echo "=== In-cluster health check ==="
kubectl run "job-platform-curl-test-${ENV}" --rm -i --restart=Never -n "${NAMESPACE}" \
  --image=curlimages/curl:8.5.0 --command -- \
  curl -sf "http://api.${NAMESPACE}.svc.cluster.local:8000/health"

echo ""
echo "Deploy complete (${ENV})."
echo "External URL (after cloudflared route): ${HEALTH_URL}"
kubectl get pods -n "${NAMESPACE}"
