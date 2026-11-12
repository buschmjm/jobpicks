# JobDeck v2 deploy runbook

Merge and deploy the stacked workstream PRs in order:

1. [A — AI performance](https://github.com/buschmjm/job-platform/compare/initial-version...cursor/workstream-a-ai-performance-d09c) (PR #3)
2. [F — Matching quality](https://github.com/buschmjm/job-platform/compare/cursor/workstream-a-ai-performance-d09c...cursor/workstream-f-matching-quality-d09c) (PR #4)
3. [B — Monetization](https://github.com/buschmjm/job-platform/compare/cursor/workstream-f-matching-quality-d09c...cursor/workstream-b-monetization-d09c) (PR #5)
4. [C — Revenue prerequisites](https://github.com/buschmjm/job-platform/compare/cursor/workstream-b-monetization-d09c...cursor/workstream-c-revenue-prerequisites-d09c) (PR #6)
5. [D+E — Instrumentation](https://github.com/buschmjm/job-platform/compare/cursor/workstream-c-revenue-prerequisites-d09c...cursor/workstream-d-instrumentation-d09c) (PR #7)
6. [Frontend integration](https://github.com/buschmjm/job-platform/compare/cursor/workstream-d-instrumentation-d09c...cursor/workstream-integration-frontend-d09c) (PR #2)

Or deploy the tip branch directly:

```bash
git checkout cursor/workstream-integration-frontend-d09c
```

## 1. Database migrations

Run in order on production Postgres:

```bash
kubectl -n jobs-platform create job --from=cronjob/migrate migrate-v2-$(date +%s) 2>/dev/null \
  || alembic upgrade head
```

Migrations **018 → 022**:

| Rev | Workstream | Changes |
|-----|------------|---------|
| 018 | A | `llm_call_logs`, score components on queue |
| 019 | F | `seniority_int`, `is_stretch` |
| 020 | B | Stripe subscription columns |
| 021 | C | Referral codes, unsubscribe tokens |
| 022 | — | Backfill `seniority_int` on jobs/profiles |

## 2. Secrets

Update `job-platform-secrets` (see `deploy/secrets/job-platform-secrets.secret.yaml.template`):

| Variable | Required for |
|----------|----------------|
| `STRIPE_SECRET_KEY` | Pro checkout |
| `STRIPE_WEBHOOK_SECRET` | Subscription webhooks |
| `STRIPE_PRICE_ID_MONTHLY_999` | $9.99/mo A/B arm |
| `STRIPE_PRICE_ID_MONTHLY_1499` | $14.99/mo A/B arm |
| `METRICS_TOKEN` | Prometheus scrape auth (`X-Metrics-Token`; falls back to `INTERNAL_EVENTS_TOKEN`) |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` | Digest + intraday alerts |
| `EMAIL_FROM` | Must match verified sending domain (see [email-deliverability.md](email-deliverability.md)) |

Stripe webhook endpoint: `https://jobs.jbuschmann.com/api/billing/webhook`

Events to enable: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`

## 3. Cluster deploy

```bash
cd ~/job-platform
git pull
make homelab-deploy
```

Verify:

```bash
curl -sf https://jobs.jbuschmann.com/health
curl -sf https://jobs.jbuschmann.com/api/billing/status -H "Authorization: Bearer $TOKEN"
curl -sf https://jobs.jbuschmann.com/metrics -H "X-Metrics-Token: $METRICS_TOKEN" | head
bash deploy/scripts/verify-smtp.sh
```

## 4. Cron schedules

| CronJob | Schedule | Purpose |
|---------|----------|---------|
| `daily-email` | `30 * * * *` | Per-timezone digest (6 AM local) |
| `queue-topup` | nightly | Deck refill + intraday Pro alerts |

## 5. Post-deploy smoke

- [ ] Onboarding with `?ref=CODE` applies referral
- [ ] Settings shows Pro upgrade / referral share
- [ ] Search page returns ranked results
- [ ] Deck cards show stretch badge where applicable
- [ ] Pro users see score breakdown on cards
- [ ] Admin dashboard shows referral + digest metrics (`/admin` + `X-Admin-Secret`)
- [ ] Prometheus scrapes `jobdeck_*` metrics from `/metrics`
- [ ] `deploy/scripts/verify-smtp.sh` passes with production SMTP secrets
- [ ] SPF/DKIM/DMARC published for `EMAIL_FROM` domain ([email-deliverability.md](email-deliverability.md))
- [ ] `bash deploy/scripts/verify-well-known.sh` passes for product domain ([mobile-launch-checklist.md](mobile-launch-checklist.md))

## 6. Homelab-infra

Ensure `jobs.jbuschmann.com` is in `cluster/thenetwork/platform/cloudflared/configmap.yaml`:

```yaml
      - hostname: jobs.jbuschmann.com
        service: http://api.jobs-platform.svc.cluster.local:8000
```

Then sync tunnel routes and restart cloudflared.
