# Cloudflare Zero Trust tier matrix

**Audit date:** 2026-08-28  
See [2026-08-28-findings.md](./2026-08-28-findings.md)

| Tier | Policy | Hostnames |
|------|--------|-----------|
| **Public product** | App auth + WAF; no CF Access required | wrensrootandrise.com, jobs.jbuschmann.com |
| **Household** | CF Access email allowlist + app login | mealie, nextcloud, jellyfin, budget, vault, seerr |
| **Infra/admin** | CF Access + oauth2-proxy or OIDC roles | n8n, ollama, git, monitoring, logs, openui |
| **Demo** | CF Access IP allowlist or disable route | moveanchor UI, wmsdemo, wrr-dev |

## Currently protected by CF Access (confirmed)

- openhands.jbuschmann.com — redirects to cloudflareaccess.com

## Dashboard actions required

1. Export all Zero Trust Access applications to git (manual screenshot or API).
2. Remove duplicate Public Hostnames that conflict with `cloudflared/configmap.yaml`.
3. Add CF Access to P0 hosts: ollama, n8n, git (until oauth2-proxy deployed).
4. Document jobs.jbuschmann.com Access policy if present (not in git).
