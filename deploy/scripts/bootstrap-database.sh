#!/usr/bin/env bash
# Create jobs_platform database + user on host Postgres (thenetwork).
# Uses docker chroot + su postgres when passwordless sudo is unavailable.
#
# Usage: ./deploy/scripts/bootstrap-database.sh [db_password]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

DB_NAME="${DB_NAME:-jobs_platform}"
DB_USER="${DB_USER:-jobs_platform}"
DB_PASS="${1:-${JOBS_PLATFORM_DB_PASSWORD:-}}"

if [[ -z "${DB_PASS}" ]]; then
  DB_PASS="$(openssl rand -hex 16)"
fi

PASS_FILE="${REPO_ROOT}/deploy/secrets/.db-password"
mkdir -p "$(dirname "${PASS_FILE}")"
printf '%s' "${DB_PASS}" > "${PASS_FILE}"
chmod 600 "${PASS_FILE}"
echo "Wrote DB password to ${PASS_FILE} (server-local, gitignored)"

psql_as_postgres() {
  if sudo -n -u postgres psql "$@" 2>/dev/null; then
    return 0
  fi
  if [[ "$(id -u)" -eq 0 ]]; then
    su - postgres -c "psql $(printf ' %q' "$@")"
    return
  fi
  if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
    local cmd="psql"
    for arg in "$@"; do
      cmd+=" $(printf '%q' "$arg")"
    done
    docker run --rm --privileged -v /:/host ubuntu:24.04 bash -c \
      "chroot /host su - postgres -c $(printf '%q' "$cmd")"
    return
  fi
  echo "ERROR: need sudo -u postgres, root, or docker" >&2
  return 1
}

ROLE_SQL="DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}'; ELSE ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASS}'; END IF; END \$\$;"
psql_as_postgres -v ON_ERROR_STOP=1 -d postgres -c "${ROLE_SQL}"

if ! psql_as_postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1; then
  psql_as_postgres -v ON_ERROR_STOP=1 -d postgres -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
fi

psql_as_postgres -v ON_ERROR_STOP=1 -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql_as_postgres -d "${DB_NAME}" -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"

echo ""
echo "Database ready. Run: ./deploy/scripts/init-homelab-secrets.sh"
