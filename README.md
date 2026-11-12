# JobPicks

**JobPicks** (earlier name: JobDeck) is a job discovery product: a swipe deck for US job matching, an apply to-do list, and AI-assisted career tools. It runs on the homelab at **https://jobs.jbuschmann.com** (`jobs-platform` namespace on thenetwork k3s).

> **Open source under the MIT License.** This is the code behind JobPicks at [jobs.jbuschmann.com](https://jobs.jbuschmann.com/jobpicks/welcome). Fork it, adapt it, and run it for your own needs. The deploy scripts and manifests target my homelab (k3s, Keycloak, Ollama, PostgreSQL with pgvector), so expect to swap hosts, realms and secrets for your own. See [LICENSE](LICENSE).

The full product thesis, market research, phase gates, and legal notes live in [plan.md](plan.md). Implementation specs for recent workstreams are in [docs/](docs/). **Orchestrator single source of truth:** [docs/research-brief-v2.1.md](docs/research-brief-v2.1.md) (pricing, mobile, launch, auditor sign-off).

---

## What it is (business)

### Problem

Job seekers drown in irrelevant listings, ghost posts, and application busywork. Incumbents optimize for engagement or employer spend, not candidate outcomes.

### Wedge

JobPicks competes on **recommendation quality and trust**, not index size:

- A daily swipe ritual over a curated US corpus
- Deterministic scoring against the user's profile (experience, skills, seniority, constraints)
- Longitudinal preference learning from swipes, dwell time, and rejection reasons
- Human-in-the-loop apply flow — JobPicks never submits applications unattended

### Beachhead

**US-wide, user-driven role targeting.** There is no fixed engineering niche in ingest. Each user's `target_titles` register global search terms; the shared corpus grows from accumulated titles plus nightly board sweeps.

### Revenue model (planned)

| Stage | Model |
|-------|--------|
| Now (Phase 2 beta) | Free for invited users |
| Phase 3 | Candidate **Pro** ~$3–6/mo (more daily matches, deeper explanations, alerts) |
| Phase 6+ | **Employer-funded** primary: job slots + ranked candidate recommendations (opt-in talent pool) |

Candidate subscriptions offset costs; employer revenue is the long-term income plan. See [plan.md §3](plan.md) for economics and kill criteria.

### Explicit non-goals

- Scraping LinkedIn, Indeed, Glassdoor, or ZipRecruiter
- Unattended auto-apply or CAPTCHA solving
- Feed ads or selling candidate data
- Real-time LLM scoring at deck-build time

---

## What is running today (September 2026)

### Production stack

| Layer | Detail |
|-------|--------|
| **URL** | https://jobs.jbuschmann.com |
| **Auth** | Keycloak OIDC (`homelab` realm, client `job-platform`); token exchange proxied through API (Cloudflare blocks direct browser → Keycloak token calls) |
| **API** | FastAPI (`deployment/api`), serves built React SPA from `web/dist/` |
| **Worker** | Long-running queue consumer (`deployment/worker`) + CronJobs |
| **Database** | PostgreSQL 16 + pgvector on thenetwork host (`localhost`) |
| **Inference** | Ollama on thenetwork (`qwen3:8b` chat, embedding model via `OLLAMA_*` config) |
| **Research** | SearXNG (career advisor web grounding) |
| **Ingress** | Cloudflare Tunnel → `api.jobs-platform.svc.cluster.local:8000` |
| **Image** | `job-platform:latest` built locally, imported into k3s via `deploy/k8s/overlays/homelab/import-images-job.yaml` |

### Live corpus (approximate)

| Source | Job source rows | Nightly sweep? | Notes |
|--------|-----------------|----------------|-------|
| Greenhouse | ~2,100 | Yes | ~20 curated boards in `seeds/companies.yaml` |
| Adzuna | ~1,600 | No (term ingest only) | Keys optional; used when users add target titles |
| JSearch | ~200 | No | **`JSEARCH_ENABLED=false`** by default (paid tier avoided) |
| USAJOBS | ~36 | Yes (if keyed) | Up to 5 pages/run; `max_days_old=1` nightly |
| Remotive | ~10 | Yes | Single feed fetch |
| Lever | ~1 | Yes | Several board tokens 404 (expected noise) |

**~2,080 open jobs** in corpus; **1 onboarded user** (private beta).

### Nightly pipeline (America/Chicago)

| CronJob | Schedule | Purpose |
|---------|----------|---------|
| `ingest` | 1:00 AM | Board sweep: Remotive + Greenhouse/Lever + USAJOBS |
| `normalize-embed` | 2:30 AM | LLM normalize job text + batch embeddings |
| `retention` | 3:30 AM | Close/delete jobs older than 30 days from `date_posted` |
| `score` | 4:00 AM | Corpus health log; enqueues `cron_queue_topup` |
| `queue-topup` | 5:00 AM | Append ≤30 scored jobs/day per active user |
| `daily-email` | 6:30 AM | "N new jobs" digest (requires SMTP secrets) |
| `queue-expiry` | hourly | Expire stale queue cards (60-day window) |
| `source-health` | hourly | Probe adapter reachability |
| `geocode-jobs` | every 4h | Backfill lat/lon for commute scoring |

The worker deployment also runs `python -m workers.consumer`, processing `queue_jobs` (backfill, term ingest, packet generation, normalize batches, etc.).

---

## Product flows (implemented)

### 1. Onboarding

1. Keycloak sign-in → `/onboarding`
2. Resume upload (PDF/DOCX) → LLM extraction with per-field confirmation
3. Questionnaire (remote preference, salary floor, commute, work auth, target titles)
4. **Queue backfill** enqueues asynchronously: score open corpus against profile, seed deck (up to 30-day window)

### 2. Swipe deck (`/deck`)

- `GET /api/deck/next` — next queue card (core + explore slots)
- `POST /api/deck/swipe` — right / left / super-like with optional reason chips
- Dwell tracking, expandable job detail, job description on demand
- **Scoring is deterministic** at queue-build time (`core/scoring.py`); no persisted per-user score table

**Match thresholds (steady state):**

- Core cards: `min_match_score = 0.35`
- Explore slots (~10%): down to `0.25`
- Weights: semantic 38%, skills 27%, level 15%, comp 10%, geo 5%, title 5%

Hard filters (never violated): blocked companies, US-only, work authorization, remote-only when user chose remote-only.

### 3. Apply to-do (`/todo`)

- Right-swipes land on the apply list
- Per-item **application steps** checklist (template + custom)
- Tracked apply click + self-report (applied / archived)
- Preference engine learns from todo outcomes

### 4. Application prepare (`/todo/:id/prepare`) — Phase 5 partial

- `POST /api/todo/{id}/packet` — async packet generation (resume tailor + apply assist + saved answers)
- Prepare UI: review/edit answers, cover letter, copy application kit
- `POST /api/todo/{id}/packet/open` — marks packet opened, returns apply URL
- **Not yet shipped:** Apply Browser with DOM bulk-fill ([docs/apply-packet-implementation-plan.md](docs/apply-packet-implementation-plan.md))

### 5. Career advisor (`/advisor/chat`)

- Streaming chat with profile + job context
- Optional SearXNG research (`ADVISOR_RESEARCH_ENABLED=true`)
- Separate from deck scoring — advisory only

### 6. Resume builder (`/advisor/build`)

- Multi-turn chat with live HTML preview
- **Resume variants** (e.g. TPM vs engineering emphasis)
- Proposal cards → apply/reject structured resume updates

### 7. Settings, privacy, admin

- Preferences, target titles, blocked companies, hard constraints
- `DELETE` privacy flow (GDPR-style erasure)
- Admin routes: user metrics, source health, quota visibility

---

## Ingest architecture

```
Free sources                Nightly sweep (max_days_old=1)
─────────────               ──────────────────────────────
Remotive feed        ──┐
Greenhouse boards    ──┼──► ingest.runner ──► pipeline ──► Postgres jobs
Lever boards         ──┤         │              (dedupe, US filter,
USAJOBS (optional)   ──┘         │               normalize hash)
                                 │
User adds target title ─────────► term_ingest (Adzuna + Remotive, quota-budgeted)
```

**Locked nightly rules** ([docs/board-sweep-scoring-implementation-plan.md](docs/board-sweep-scoring-implementation-plan.md)):

- `NIGHTLY_MAX_DAYS_OLD = 1` — only yesterday's postings enter the corpus each night
- Corpus retained **30 days** from `date_posted`, then closed + deleted
- `apply_freshness_lifecycle` (3-miss close) is **skipped** on nightly sweep — date retention handles staleness
- USAJOBS: no keyword, pages 1–5, requires `USAJOBS_API_KEY` + `USAJOBS_USER_AGENT`
- JSearch off unless `JSEARCH_ENABLED=true`

**USAJOBS ops:**

```bash
# Request key (emails Authorization-Key)
./deploy/scripts/request-usajobs-api-key.sh

# Test + apply to k8s secret + optional one-off ingest
USAJOBS_API_KEY=... RUN_INGEST=1 ./deploy/scripts/bootstrap-usajobs-api-key.sh
```

Nightly `max_days_old=1` only ingests federal postings from the last 24 hours. For initial backfill, run a one-off import with a wider window (28–60 days).

---

## Repository layout

```
api/           FastAPI routers, services, repositories, email templates
core/          SQLAlchemy models, scoring, queue builder, preference engine
ingest/        SourceAdapter interface + adapters (adzuna, jsearch, remotive,
               greenhouse, lever, usajobs)
inference/     Ollama client, resume/career prompts, embeddings, extraction
workers/       Queue consumer + cron entrypoints (ingest, score, topup, …)
web/           React + Vite + TypeScript + Tailwind v4 SPA ("JobPicks")
prompts/       Versioned LLM prompt files
migrations/    Alembic (current head: 020_monetization)
deploy/        k8s manifests (kustomize), secrets templates, deploy scripts
seeds/         companies.yaml (ATS boards), search_terms.yaml, city centroids
tests/         pytest (adapters, scoring, API, workers)
docs/          Implementation plans (board sweep, apply packet)
plan.md        Master product spec — read before changing product behavior
```

---

## Local development

### Prerequisites

- Python 3.12+
- PostgreSQL 16+ with `pgvector`
- Ollama (or point `OLLAMA_BASE_URL` at thenetwork)
- Node 20+ (frontend)

### Backend

```bash
cd job-platform
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # DATABASE_URL, OLLAMA_BASE_URL, SECRET_KEY, …
alembic upgrade head
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd web && npm install && npm run dev
# http://localhost:5173 — proxies /api → :8000
```

### Worker (local)

```bash
python -m workers.consumer
```

### Quality

```bash
ruff check api core ingest inference workers tests
mypy api core ingest inference workers
pytest -v
```

---

## Homelab deploy

```bash
# From dev machine (syncs repo + runs full deploy on thenetwork)
make homelab-deploy

# On thenetwork (step-by-step)
./deploy/scripts/bootstrap-database.sh
./deploy/scripts/init-homelab-secrets.sh    # needs JOBS_PLATFORM_DB_PASSWORD
./deploy/scripts/deploy-on-server.sh        # build, import image, migrate, rollout
./deploy/scripts/apply-cloudflared-route.sh # jobs.jbuschmann.com
```

**Before first deploy:**

1. Create `deploy/secrets/job-platform-secrets.secret.yaml` via `init-homelab-secrets.sh`
2. Add ingest keys: `USAJOBS_API_KEY`, optional `ADZUNA_*`, `JSEARCH_*` (keep JSearch off unless budgeted)
3. Add SMTP vars for daily email (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`)
4. Register Keycloak client `job-platform` (confidential, redirect `https://jobs.jbuschmann.com/auth/callback`)

**Smoke test:**

```bash
curl -sf https://jobs.jbuschmann.com/health
kubectl get pods,cronjob -n jobs-platform
```

**Image pull note:** k3s uses `imagePullPolicy: IfNotPresent` with a locally imported tag. After `docker build`, always run the import job or `deploy-on-server.sh` — otherwise new pods may hit `ImagePullBackOff` trying docker.io.

---

## Where we are vs plan phases

| Phase | Status |
|-------|--------|
| **0** Setup spike | Done |
| **1** Concierge | Done (informed API/source choices) |
| **2** V1 build (E2.1–E2.13) | **Complete** — private beta live |
| **3** Monetization (Stripe Pro) | **Complete** (Workstream B) — checkout, portal, entitlements |
| **4** Growth (SEO pages, referrals) | **Partial** — referrals + digest done (Workstream C); SEO pages pending |
| **5** Application assist | **Partial** — packets + prepare UI; apply browser pending |
| **6** Employer side | Not started (committed destination per plan) |

### Phase 2 checklist (E2 epics)

| Epic | Status |
|------|--------|
| E2.1 Scaffold + k8s | Done |
| E2.2 Schema + migrations | Done (022 revisions) |
| E2.3 Ingest framework + Adzuna/JSearch/Remotive | Done |
| E2.4 GH/Lever/USAJOBS + dedupe | Done (USAJOBS live Sep 2026) |
| E2.5 Inference (resume parse, embed, circuit breaker) | Done |
| E2.6 Scoring engine | Done (profile-first weights) |
| E2.7 Preference engine | Done |
| E2.8 Queue builder (backfill, topup, expiry) | Done |
| E2.9 Auth + onboarding | Done (Keycloak replaces magic link in prod) |
| E2.10 Swipe deck + todo UI | Done |
| E2.11 Daily email | Built; **SMTP not configured** in cluster |
| E2.12 Events + admin + source health | Done |
| E2.13 Privacy (delete, retention) | Done |

---

## JobPicks v2 workstreams (A→F→B→C→D→E)

Stacked branches on `job-platform` (merge in order):

| Workstream | Branch | Scope |
|------------|--------|-------|
| A | `cursor/workstream-a-ai-performance-d09c` | LLM telemetry, load control, qwen3:4b |
| F | `cursor/workstream-f-matching-quality-d09c` | Seniority, attainability, search API, stretch |
| B | `cursor/workstream-b-monetization-d09c` | Stripe Pro, entitlements, score breakdown gating |
| C | `cursor/workstream-c-revenue-prerequisites-d09c` | Referrals, digest timezone, unsubscribe, cancel |
| D+E | `cursor/workstream-d-instrumentation-d09c` | Client events, Prometheus, admin metrics |
| Frontend | `cursor/workstream-integration-frontend-d09c` | Web UI for billing, search, referrals, instrumentation |

**Deploy:** run migrations `018` → `022` in order. See [docs/jobdeck-v2-deploy.md](docs/jobdeck-v2-deploy.md) for the full runbook (Stripe, SMTP, tunnel, smoke tests).

---

## Roadmap (next)

1. **Apply Browser** — session + bulk-fill confirmed packet into Greenhouse/Lever forms ([docs/apply-packet-implementation-plan.md](docs/apply-packet-implementation-plan.md))
2. **SMTP + daily digest** — wire homelab/GCP SMTP secrets; verify open tracking
3. **Closed beta expansion** — invite flow via Dashy "Request Access" → Keycloak `jobs` role only
4. **Matching quality iteration** — tune weights/thresholds from swipe feedback (runtime config E2)
5. **SEO landing pages** — Phase 4 growth (public job pages)
6. **JSearch decision** — stay off free tier until user count justifies $25/mo API spend
7. **GCP migration trigger** — when GPU night window or Postgres load exceeds homelab comfort
8. **Phase 6 discovery** — employer interviews before any employer-facing build

---

## Key environment variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres connection |
| `OLLAMA_BASE_URL` / `OLLAMA_CHAT_MODEL` | LLM + embeddings |
| `AUTH_BACKEND` | `keycloak` in production |
| `KEYCLOAK_*` | OIDC issuer, client, realm |
| `USAJOBS_API_KEY` / `USAJOBS_USER_AGENT` | Federal jobs nightly sweep |
| `JSEARCH_ENABLED` | `false` unless explicitly enabling paid API |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Term ingest only |
| `SMTP_*` / `EMAIL_FROM` | Daily digest |
| `GOOGLE_MAPS_API_KEY` | Commute enrichment (optional) |
| `SEARXNG_BASE_URL` | Advisor research |
| `ADVISOR_RESEARCH_ENABLED` | Toggle web search in career chat |

See `.env.example` and `deploy/secrets/job-platform-secrets.secret.yaml.template`.

---

## Related homelab docs

- Dashy tile + landing page: `homelab-infra/site-pages/jobdeck/`
- Keycloak `jobs` role isolation: `homelab-infra/docs/runbooks/jobs-keycloak-audit.md`
- SSO runbook: `homelab-infra/docs/runbooks/keycloak-sso.md`

---

## License / access

Private homelab software. Not open source. Access by invitation only.
