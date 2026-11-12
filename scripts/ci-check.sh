#!/usr/bin/env bash
# Same checks as .forgejo/workflows/ci.yml and .github/workflows/ci.yml
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

echo "=== Ruff ==="
ruff check api core ingest inference workers tests

echo "=== Mypy ==="
mypy api core ingest inference workers

echo "=== Pytest ==="
pytest -q

echo "=== Web (lint, test, build) ==="
(
  cd web
  npm ci
  npm run lint
  npm test
  npm run build
)

echo "All CI checks passed."
