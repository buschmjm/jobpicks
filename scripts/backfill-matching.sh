#!/usr/bin/env bash
# One-shot: normalize/embed corpus, then re-queue deck for a user.
#
# Usage:
#   ./scripts/backfill-matching.sh --email user@example.com
#   ./scripts/backfill-matching.sh --user-id <uuid> --clear-queued
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

NORMALIZE_ROUNDS="${NORMALIZE_MAX_ROUNDS:-20}"
NORMALIZE_BATCH="${NORMALIZE_BATCH_SIZE:-50}"
EMBED_BATCH="${EMBED_BATCH_SIZE:-200}"

echo "=== Normalizing job corpus (${NORMALIZE_ROUNDS} rounds max) ==="
NORMALIZE_MAX_ROUNDS="${NORMALIZE_ROUNDS}" \
  NORMALIZE_BATCH_SIZE="${NORMALIZE_BATCH}" \
  EMBED_BATCH_SIZE="${EMBED_BATCH}" \
  python -m workers.jobs.normalize_embed

echo "=== Rebuilding user deck ==="
python scripts/rebackfill_user.py "$@"

echo "Done. Worker will process queue_backfill shortly."
