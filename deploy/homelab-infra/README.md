# Homelab-infra integration for job-platform

Copy or merge these into [homelab-infra](https://github.com/buschmjm/homelab-infra) on thenetwork.

## 1. Cloudflared route

Add to `cluster/thenetwork/platform/cloudflared/configmap.yaml` **before** the `http_status:404` catch-all:

```yaml
      - hostname: jobs.jbuschmann.com
        service: http://api.jobs-platform.svc.cluster.local:8000
```

Then apply and restart:

```bash
cd ~/homelab-infra
kubectl apply -f cluster/thenetwork/platform/cloudflared/configmap.yaml
kubectl -n cloudflared rollout restart deployment/cloudflared
# Optional: sync routes to Cloudflare API
# CLOUDFLARE_API_TOKEN=... ./scripts/sync-homelab-tunnel-routes.sh
```

## 2. Secrets manifest entry (optional)

Add to `secrets/manifest.yaml`:

```yaml
  - namespace: jobs-platform
    name: job-platform-secrets
    file: jobs-platform-job-platform-secrets
    encrypt: true
    apply: true
    notes: Job platform DB URL, SECRET_KEY, ingest API keys, SMTP
```

Copy template:

```bash
cp /path/to/job-platform/deploy/secrets/job-platform-secrets.secret.yaml.template \
   ~/homelab-infra/secrets/templates/jobs-platform-job-platform-secrets.secret.yaml.template
```

On thenetwork, prefer `job-platform/deploy/scripts/init-homelab-secrets.sh` which applies directly to the cluster.

## 3. Host Postgres

Run once on thenetwork (requires postgres superuser):

```bash
cd ~/job-platform
./deploy/scripts/bootstrap-database.sh
# Save printed password, then:
JOBS_PLATFORM_DB_PASSWORD=... ./deploy/scripts/init-homelab-secrets.sh
```

Or use homelab-infra helper:

```bash
cd ~/homelab-infra
sudo ./scripts/enable-pgvector-host-postgres.sh jobs_platform
```

## 4. Deploy from workstation

```bash
cd ~/job-platform
make homelab-deploy
# First time, with DB password:
JOBS_PLATFORM_DB_PASSWORD=... make homelab-deploy
```

## 5. Smoke test

```bash
curl -sf https://jobs.jbuschmann.com/health
curl -sf https://jobs.jbuschmann.com/api/health
open https://jobs.jbuschmann.com/
```

Admin dashboard: `https://jobs.jbuschmann.com/admin` with `X-Admin-Secret` header.
