#!/usr/bin/env bash
# Deactivate legacy DevOps search terms seeded before user-driven ingest.
#
# Usage on thenetwork:
#   ./deploy/scripts/deactivate-legacy-search-terms.sh
#
# Or via kubectl:
#   kubectl exec -n jobs-platform deployment/api -- python -c "..."
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

if kubectl get deployment api -n jobs-platform >/dev/null 2>&1; then
  kubectl exec -n jobs-platform deployment/api -- python -c "
from core.database import SessionLocal
from core.models import SearchTerm
from sqlalchemy import select, update

session = SessionLocal()
try:
    rows = session.scalars(
        select(SearchTerm).where(SearchTerm.contributed_by_user_id.is_(None))
    ).all()
    count = len(rows)
    if count == 0:
        print('No legacy search terms to deactivate.')
    else:
        session.execute(
            update(SearchTerm)
            .where(SearchTerm.contributed_by_user_id.is_(None))
            .values(is_active=False)
        )
        session.commit()
        print(f'Deactivated {count} legacy search terms.')
finally:
    session.close()
"
else
  python - <<'PY'
import os
import sys

sys.path.insert(0, os.getcwd())
from core.database import SessionLocal
from core.models import SearchTerm
from sqlalchemy import select, update

session = SessionLocal()
try:
    rows = session.scalars(
        select(SearchTerm).where(SearchTerm.contributed_by_user_id.is_(None))
    ).all()
    count = len(rows)
    if count == 0:
        print("No legacy search terms to deactivate.")
    else:
        session.execute(
            update(SearchTerm)
            .where(SearchTerm.contributed_by_user_id.is_(None))
            .values(is_active=False)
        )
        session.commit()
        print(f"Deactivated {count} legacy search terms.")
finally:
    session.close()
PY
fi

echo "Done."
