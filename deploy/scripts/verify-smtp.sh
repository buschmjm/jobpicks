#!/usr/bin/env bash
# Verify SMTP configuration before enabling digest cron in production.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ "${EMAIL_BACKEND:-smtp}" == "log" ]]; then
  echo "EMAIL_BACKEND=log — SMTP checks skipped (dev/test mode)."
  exit 0
fi

: "${SMTP_HOST:?SMTP_HOST is required}"
: "${SMTP_USER:?SMTP_USER is required}"
: "${SMTP_PASSWORD:?SMTP_PASSWORD is required}"
: "${EMAIL_FROM:?EMAIL_FROM is required}"

python - <<'PY'
from api.email import SmtpConfig, email_backend_status

status = email_backend_status()
if not status.get("ready"):
    raise SystemExit(f"SMTP not ready: {status}")
cfg = SmtpConfig.from_env()
print(f"SMTP OK: {cfg.host}:{cfg.port} from={cfg.email_from} tls={cfg.use_tls} ssl={cfg.use_ssl}")
PY

echo "SMTP configuration looks ready. Send a test digest from staging before public launch."
