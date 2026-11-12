#!/usr/bin/env bash
# Fail unless GitHub Actions CI and Build image succeeded for the given commit.
#
# Usage:
#   ./deploy/scripts/verify-github-build.sh [commit-sha]
#
# Environment:
#   GITHUB_REPO   default: buschmjm/job-platform
#   SKIP_GITHUB_VERIFY=1   bypass (local emergency deploys only)
set -euo pipefail

if [[ "${SKIP_GITHUB_VERIFY:-}" == "1" ]]; then
  echo "SKIP_GITHUB_VERIFY=1 — skipping GitHub build verification"
  exit 0
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI is required to verify GitHub builds before deploy." >&2
  echo "Install gh or set SKIP_GITHUB_VERIFY=1 for emergency local deploys." >&2
  exit 1
fi

COMMIT="${1:-$(git rev-parse HEAD)}"
REPO="${GITHUB_REPO:-buschmjm/job-platform}"

require_success() {
  local workflow="$1"
  local run_id conclusion status

  run_id="$(gh run list \
    --repo "${REPO}" \
    --commit "${COMMIT}" \
    --workflow "${workflow}" \
    --event push \
    --limit 1 \
    --json databaseId,conclusion,status \
    --jq '.[0].databaseId // empty')"

  if [[ -z "${run_id}" ]]; then
    echo "ERROR: No push '${workflow}' run found for commit ${COMMIT} on ${REPO}." >&2
    echo "Push the branch and wait for GitHub Actions before deploying." >&2
    exit 1
  fi

  conclusion="$(gh run view "${run_id}" --repo "${REPO}" --json conclusion --jq '.conclusion')"
  status="$(gh run view "${run_id}" --repo "${REPO}" --json status --jq '.status')"

  if [[ "${status}" != "completed" ]]; then
    echo "ERROR: '${workflow}' is still ${status} for commit ${COMMIT} (run ${run_id})." >&2
    echo "Wait for GitHub Actions to finish, then retry deploy." >&2
    exit 1
  fi

  if [[ "${conclusion}" != "success" ]]; then
    echo "ERROR: '${workflow}' ${conclusion} for commit ${COMMIT} (run ${run_id})." >&2
    echo "Fix CI/build failures before deploying to live." >&2
    gh run view "${run_id}" --repo "${REPO}" --log-failed 2>/dev/null | tail -40 || true
    exit 1
  fi

  echo "OK: ${workflow} succeeded (run ${run_id})"
}

echo "=== Verifying GitHub Actions for ${COMMIT} (${REPO}) ==="
require_success "CI"
require_success "Build image"
echo "GitHub CI and image build are green for ${COMMIT}."
