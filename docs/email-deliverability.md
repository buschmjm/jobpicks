# Email deliverability (WS-5)

JobDeck sends **transactional/marketing hybrid** mail: daily digests and Pro intraday alerts.
Use a reputable SMTP provider (Amazon SES, Postmark, Resend, etc.) — **not** raw homelab port 25.

## Required secrets

Set in `job-platform-secrets` (see `deploy/secrets/job-platform-secrets.secret.yaml.template`):

| Variable | Example | Notes |
|----------|---------|-------|
| `SMTP_HOST` | `email-smtp.us-east-1.amazonaws.com` | Provider SMTP endpoint |
| `SMTP_PORT` | `587` or `465` | 587 → STARTTLS; 465 → SSL |
| `SMTP_USE_TLS` | `true` | Default for port 587 |
| `SMTP_USE_SSL` | `true` | Set for port 465 |
| `SMTP_USER` | *(provider username)* | |
| `SMTP_PASSWORD` | *(provider password)* | |
| `EMAIL_FROM` | `JobDeck <hello@yourdomain.com>` | Must match verified domain |

`EMAIL_BACKEND=smtp` in the cluster ConfigMap (default). Use `EMAIL_BACKEND=log` locally.

## DNS (public launch gate)

Publish these on the **same domain** as `EMAIL_FROM` (e.g. `jobs.yourdomain.com` or root domain):

1. **SPF** — authorize your SMTP provider to send for the domain.
2. **DKIM** — provider gives CNAME/TXT records; enable signing in the provider console.
3. **DMARC** — start with `p=none` monitoring, tighten to `quarantine`/`reject` after a week of clean digests.

Example DMARC monitor record:

```txt
_dmarc.yourdomain.com  TXT  "v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com"
```

## List-Unsubscribe headers

Digest and intraday emails include `List-Unsubscribe` and `List-Unsubscribe-Post` (RFC 8058)
pointing at `/api/email/unsubscribe/{token}`. Gmail/Yahoo require this for bulk senders.

## Verify before deploy

```bash
# From repo root with SMTP env loaded:
bash deploy/scripts/verify-smtp.sh

# Or hit the authenticated status endpoint after login:
curl -sf https://jobs.jbuschmann.com/api/email/status -H "Authorization: Bearer $TOKEN"
```

## Cron

`daily-email` CronJob runs hourly (`30 * * * *`) and sends per-user around **6 AM local**
(see `core/digest_schedule.py`). Requires worker image + secrets (patched via kustomize).

## User preferences

- Users can disable digests in **Settings** or via the unsubscribe link in any email.
- `unsubscribed_at` on `users` blocks digest + intraday alerts.
- Consent events: `digest_subscribed` / `unsubscribed` in the `events` table.
