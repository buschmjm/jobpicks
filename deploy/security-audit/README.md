# Security audit automation

Re-runnable homelab security audit. **Canonical location:** [homelab-infra](https://github.com/buschmjm/homelab-infra) on thenetwork.

## Run on thenetwork

```bash
cd ~/homelab-infra
./scripts/security-audit/run-all.sh
```

Artifacts land in `docs/security-audit/`.

## Scripts

| Script | Purpose |
|--------|---------|
| `collect-inventory.sh` | Keycloak clients/roles + git cloudflared routes |
| `probe-hostnames.sh` | Anonymous HTTP probes + sensitive paths |
| `test-isolation.sh` | Temporary KC users + expected role matrix |
| `collect-secrets-inventory.sh` | K8s secret names (no values) |
| `collect-host-audit.sh` | Ports, firewall, privileged pods |
| `run-all.sh` | Runs all phases |

## Latest findings

See [2026-08-28-findings.md](./2026-08-28-findings.md).

**Top critical:** Ollama public inference, Forgejo anonymous API, Postgres 0.0.0.0:5432.
