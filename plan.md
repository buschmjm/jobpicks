# AI Job Discovery Platform — Master Plan (v1)

> **Purpose of this document:** This is the single source of truth for building the product.
> It contains every decision already made, the rationale, and the exact work breakdown so
> that implementation agents (Composer, etc.) can execute tasks WITHOUT making product,
> architecture, or business decisions themselves. If a task requires a decision not
> covered here, the agent must STOP and ask the owner rather than improvise.
>
> Research date: 2026-08-27. Facts below were verified online on that date and are
> labeled. Everything is tagged **[FACT]**, **[ASSUMPTION]**, or **[SPECULATION]**.
>
> **Revision 2 (2026-08-27):** updated after reviewing the owner's `homelab-infra` repo
> and two existing n8n prototypes. Changes: (a) hardware reality — the "desktop" and the
> homelab are the SAME single host (`thenetwork`, k3s + host-level Ollama, GTX 1660
> Super / 6GB VRAM) → model picks and scheduling revised in §9/§13; (b) business model
> revised to **employer-funded primary / cheap candidate Pro ($3–6/mo) secondary** with
> validation in §3; (c) data strategy re-tiered to **bulk aggregator APIs first**
> (Adzuna, JSearch, Remotive — matching the owner's proven n8n workflow) in §8;
> (d) product scope expanded to a **browse-and-apply web platform**, not digest-only
> (§5); (e) n8n is a prototype/reference only — the platform is real code (§18).
>
> **Revision 3 (2026-08-27):** owner clarifications. (a) **n8n is fully out** — the
> workflows were shared only to show which APIs the owner already has accounts/keys
> for; nothing runs on n8n in any phase; the entire product is the coded application
> defined here. (b) The core UX is a **swipe deck ("Tinder for jobs")** feeding a
> per-user job queue — research verdict in §5. (c) **New-user cold start: backfill the
> last 4 weeks (28 days) of matching jobs** into the user's queue as training data;
> thereafter each day's newly posted matches are appended to the queue. (d) Right-swipes
> build an **Apply To-Do list** — the v1 apply flow. (e) Resume upload is a mandatory
> onboarding step (unchanged, now emphasized).
>
> **Revision 4 (2026-09-04):** Product renamed to **JobPicks** (see §19). Domains
> `jobpicks.com` / `.app` appear available; JobMatcher rejected (`jobmatcher.app`
> competitor); CustomJobs retained as naming fallback only. Play Store marketing page
> at `/welcome`; listing copy in `docs/store-listing/`.
> and OpenWebNinja API keys in plaintext. Rotate both keys and move them into the
> homelab-infra secrets workflow (SOPS / `secrets/local/`) before anything else.

---

## 1. Executive Verdict

**Conditional yes — build it, but as a narrow, niche, candidate-side recommendation
product with hard validation gates. Do NOT build a marketplace, employer tools, or
auto-apply in v1. Treat "replace my income" as a Phase-4+ outcome that must be earned
by retention and willingness-to-pay data, not assumed.**

Why conditional and not a strong yes:

1. **The space is crowded and free.** [FACT] Jobright.ai claims 2,000,000+ users, an
   8M+ job index with ~400k new jobs/day, AI matching, 1-click autofill, tailored
   resumes, referral finding, and an AI copilot — with a free tier. [FACT] Teal claims
   4M+ users with a free tier and paid plans at $13/week, $29/30 days, $79/90 days.
   [FACT] hiring.cafe indexes ~3.96M jobs from ~124.5k companies **directly from
   employer career pages/ATS systems**, is free, has AI search, salary/benefits/YOE
   filters, and explicitly markets itself as "our quest to destroy Indeed and LinkedIn."
   "AI job matching" as a category is no longer novel. A generic clone loses.
2. **Incumbents are enormous.** [FACT] LinkedIn revenue was US$17.8B in FY2025
   (Microsoft annual report) with 1.3B registered members (~230M in the US). [FACT]
   ZipRecruiter is a public company (NYSE: ZIP) doing hundreds of millions in annual
   revenue on an employer-pays model. Distribution, not technology, is their moat.
3. **But the wedge is real.** None of the incumbents, and none of the AI startups
   researched, do deep **longitudinal preference learning with time-decayed behavioral
   signals and explicit rejection-reason taxonomy** ("not qualified" vs "bad comp" vs
   "don't want this kind of work"). Jobright/Teal are resume-tooling-first; hiring.cafe
   is filter/search-first; LinkedIn optimizes for engagement and recruiter revenue, not
   candidate outcomes. A product whose entire job is *"5 great jobs in your inbox every
   morning, and it gets smarter every time you react"* is a defensible **experience**
   wedge for a niche, even if not a technology moat. [ASSUMPTION]
4. **Your cost structure is good, with one hard ceiling.** Ollama + k3s + Postgres all
   run on one homelab host (`thenetwork`) with a GTX 1660 Super (6GB VRAM) — near-zero
   marginal AI cost during validation, but only small models fit (§9), and every
   GPU-hour competes with the rest of the homelab. This is fine for v1 batch pipelines;
   it is NOT fine for real-time chat features — don't build those yet. [FACT about your
   setup]
5. **The revenue destination is the employer side.** The entire industry's economics
   prove candidates don't pay much but employers pay a lot ([FACT] LinkedIn $17.8B,
   ZipRecruiter hundreds of $M — both overwhelmingly employer-funded). The candidate
   product is the audience-builder; employers posting jobs and buying candidate
   recommendations are the business (§3).

**The single most important instruction in this plan:** the smallest experiment that can
kill or confirm this business is Phase 1 (manual concierge, ~2 weeks, near-zero code).
Do not let agents build ahead of the current phase.

---

## 2. Market Reality (research summary)

### Incumbents
| Player | Model | Scale | Notes |
|---|---|---|---|
| LinkedIn | Recruiter seats, job ads, Premium subs, ads | [FACT] $17.8B rev FY2025; 1.3B members; Premium subscriptions grew 85% 2019→2023 | Candidate experience is a byproduct; revenue comes from recruiters/employers. Also [FACT] fought scrapers in court for years (hiQ v. LinkedIn) — never build on scraping LinkedIn. |
| Indeed (Recruit Holdings) | Pay-per-click/pay-per-application job ads | Largest job site by traffic [ASSUMPTION, widely reported] | Aggregator + employer ads. |
| ZipRecruiter | Employer SaaS subscriptions + job distribution | [FACT] Public co; $418M revenue in 2020 (grew after); 2023 layoffs of 20% signal market contraction | Employer-pays; matching AI marketed since 2018. |
| Glassdoor/Dice/Wellfound/BuiltIn | Employer listings/branding | Niche | Dice (tech) has been in long decline [ASSUMPTION]. |

### AI-native candidate tools (the actual competition)
| Product | What it does | Pricing | Read |
|---|---|---|---|
| Jobright.ai | Match scores, autofill apply, tailored resumes, insider referrals, AI copilot ("Orion"), H1B filter; employer side exists | Freemium; paid tier (~$20–40/mo range) [ASSUMPTION on exact price] | [FACT] Claims 2M users, 8M jobs, 400k/day. Closest analog to this idea. Breadth-first, shallow personalization. |
| Teal | Resume builder, job tracker, keyword match scoring, autofill | [FACT] Free + $13/wk / $29/30d / $79/90d | Tooling-first, not recommendation-first. 4M+ users claimed. |
| hiring.cafe | Search engine over ~4M jobs pulled straight from employer career sites; extreme filtering; AI search | [FACT] Free | Proves the ATS-direct data strategy works at small-team scale. Community-driven growth (Reddit). |
| Simplify, LazyApply, AIApply, Sonara(†), etc. | Auto-apply / application spam | Various; Sonara shut down [ASSUMPTION] | Auto-apply is an arms race; employers are deploying AI to filter AI applications. Recruiters publicly complain about application floods. [ASSUMPTION based on widespread 2024–2026 reporting] |

### What job seekers complain about (Reddit/communities, qualitative) [ASSUMPTION — directionally reliable, not quantified]
- Ghost jobs / stale listings on aggregators; hiring.cafe's growth is largely a reaction to this.
- Irrelevant matches ("I'm a senior SRE, why am I seeing help-desk roles").
- Application black holes; hundreds of applications, no responses.
- Repeated re-entry of the same data into ATS forms.
- Distrust of "AI matched you 95%!" scores that are obviously keyword soup.

### Conclusions that drive this plan
1. Compete on **recommendation quality + trust + daily ritual**, not on index size,
   resume tools, or auto-apply.
2. **Niche-first is mandatory.** General-purpose = competing with Jobright's index and
   LinkedIn's network. Chosen niche: see §4.
3. **Data via legitimate ATS-direct + APIs** (see §8). hiring.cafe proves feasibility.
4. **Candidate-side first, employer-side much later.** Employer-side AI screening also
   triggers the harshest regulatory regime (see §12).

---

## 3. Business Model (decision — Revision 2)

**Decision: Employer-funded is the PRIMARY revenue model; candidate Pro is a cheap
secondary tier ($3–6/mo). Sequencing is unchanged: candidates first, employers second —
because employer money only shows up after candidate liquidity exists.**

### Is the owner's proposed model viable? (validation)
The owner's preference — "most money from companies posting jobs on the platform and
getting recommended candidates" — **is the dominant, proven model of the entire
industry**:
- [FACT] LinkedIn ($17.8B FY2025), Indeed, and ZipRecruiter are all overwhelmingly
  employer-funded (recruiter seats, job ads/slots, per-click/per-application pricing).
  Candidate subscriptions are a rounding error for all of them.
- [ASSUMPTION — verify pricing pages at Phase 6] Niche job boards commonly charge
  **$99–$500 per 30–60 day post**; ZipRecruiter-style self-serve slots run
  ~$299+/mo; sourcing/"recommended candidates" products command more.
- The catch (and it is the whole game): **employers pay for reach or qualified
  candidates, and you have neither until the candidate side works.** A two-sided
  cold-start attacked from the employer side first fails. So the model is: build the
  candidate audience free/cheap → sell employers access to it.
- Regulatory note: the moment we rank/recommend candidates TO employers, we become an
  employer-side automated employment decision tool → NYC LL144 bias-audit territory,
  Colorado AI Act, EU AI Act Annex III (§12). Budget for counsel + a bias-audit process
  at Phase 6. Mitigant: make candidate visibility **opt-in** ("open to being
  recommended") — consent-based talent pool, never surfacing users who didn't ask.

### Revenue stack (in order of expected contribution at maturity)
1. **Employer job slots (Phase 6):** self-serve posting, $99–$199/post/30d intro
   pricing in the niche [ASSUMPTION — discovery interviews will set this]. Posted jobs
   enter the same scoring pipeline and reach exactly the candidates whose learned
   preferences match — that's the pitch vs. Indeed spray-and-pray.
2. **Recommended-candidates / sourcing subscription (Phase 6+):** employer sees ranked,
   consenting candidates for their posted role, with explainable match reasons.
   $299–$499/mo per active seat [ASSUMPTION]. This is the defensible product — it
   monetizes the preference-learning data.
3. **Candidate Pro — $5/mo or $48/yr** (owner directive: $3–6 range; $5 is the test
   anchor, A/B $3 vs $6 in Phase 3): more matches/day, intraday alerts, deep
   explanations, resume-tailoring suggestions, salary intelligence. At this price it's
   a cost-offset + commitment signal, NOT the income plan.
4. Never: ads in the feed, selling candidate data (permanently rejected).

### Realistic economics (all [ASSUMPTION], conservative)

| Stage | Candidates | Candidate rev (3% paid @$5) | Employers | Employer rev | Total MRR | Infra |
|---|---|---|---|---|---|---|
| Validation | 1,000 | $150 | 0 | $0 | ~$150 | ~$0 (homelab) + ~$25–75 APIs |
| Liquidity | 10,000 | $1,500 | 15 slots + 5 sourcing seats | ~$3,500 | ~$5,000 | ~$300–800 (GCP DB, email, APIs) |
| Scale | 50,000 | $7,500 | 80 slots + 25 seats | ~$18,000 | ~$25,000 | ~$2–5k |
| Income replacement | 100,000 | $15,000 | 150 slots + 50 seats | ~$35,000 | ~$50,000 | ~$4–8k |

Read: at $3–6 candidate pricing, candidate revenue alone NEVER replaces an income at
realistic scale (100k users × 3% × $5 = $15k MRR requires beating the #1 distribution
risk massively). The employer side is what makes the numbers work — which is why Phase 6
is now a committed destination, not a maybe. Candidate churn (people get hired) matters
less in this model: the free tier keeps them as *inventory value* for employers and as
returning searchers later.

Rejected: employer-first sequencing (no audience to sell), pay-per-hire at launch
(attribution + relationships we lack; revisit as pricing option at Phase 6+), feed ads.

### Infra-cost stress test: "if every user paid $6/mo, batch at night, reuse the corpus DB" (owner question, validated 2026-08-27)

Owner asked whether $6/mo per user, nightly batch processing, and a reused/deduped job
corpus DB come out ahead under pessimistic assumptions. Answer: **yes, overwhelmingly —
infra is not, and was never going to be, the constraint on this business.** Distribution
(getting/keeping paying users) is the real risk, which is *already* why §3 makes employer
revenue the primary target. This does not change the model above; it validates it.

**Per-payer marginal cost (fully loaded, rounded up):**
| Item | Pessimistic cost/user/mo | Note |
|---|---|---|
| Stripe fee | **$0.474** | [FACT, verified live 2026-08-27: 2.9% + $0.30/charge]. On a $6 ticket that's **7.9%** of revenue — small-ticket subscriptions eat disproportionately more than the "2.9%" headline suggests, because the $0.30 fixed piece dominates. Annual billing ($60–66/yr) drops this to ~3.4%. Worth doing at Phase 3. |
| Transactional email | ~$0.01 | SES-class pricing ~$0.10/1,000 emails × ~30/mo/user [ASSUMPTION, not re-verified this session]. |
| DB/storage growth (events, embeddings) | ~$0.10 | Amortized Cloud SQL cost once off homelab; ~$0 while still on homelab Postgres. |
| Cloud LLM burst (see GPU note below) | ~$0.15 | Only needed once homelab GPU night-window is saturated; blended small-model token cost, generous rounding. |
| **Total marginal cost/payer** | **~$0.73/mo** | **Contribution margin ≈ $5.27/payer/mo (~88%), even fully loaded and pessimistic.** |

**Fixed/step costs (independent of user count within a band — this is where the shared
corpus DB and batch design actually pay off, since API cost tracks unique jobs/search
terms, not per-user calls):**
| Band | Homelab-only (0–~2k users) | Off-homelab (2k–20k) | Multi-niche (20k–100k) |
|---|---|---|---|
| JSearch + Adzuna | $0–$75 | $150–$300 | $500–$800 |
| Hosting/DB | $0 (homelab) | $100–$300 (Cloud SQL) | $800–$1,500 |
| Misc (domain, monitoring, email svc) | ~$30 | ~$50 | ~$200 |
| **Fixed total** | **~$50–$150/mo** | **~$400–$800/mo** | **~$1,500–$3,000/mo (+ likely 1 support hire)** |

**Breakeven in paying users (fixed ÷ $5.27 contribution margin):** ~10–30 payers covers
the homelab band, ~80–150 payers covers the off-homelab band, ~300–570 payers covers the
multi-niche band. At $6/mo, infra breakeven is measured in **low hundreds of paying
users**, not thousands — any real traction clears it.

**The one genuine physical (not financial) constraint:** the desktop's GTX 1660 Super
(6GB, no Tensor Cores) has a fixed nightly compute budget. Personalized swipe-card
explanations (qwen2.5:7b-instruct, ~10/user/night) are the bottleneck task, not scoring
(cheap/deterministic) or embeddings (small model). Rough math: ~10 explanations × ~150
output tokens ÷ ~15 tok/s ≈ 100s/user; a 5-hour night window ≈ 180 users' worth of
explanations before the GPU — not the budget — runs out of hours. Fix is cheap, not a
revenue problem: fall back to template explanations for most users, or burst overflow to
a hosted small model (~$0.05–0.15/user/mo, already counted above). **This caps homelab-only
operation at roughly a few hundred concurrently-active users for the explanation feature
specifically — a scheduling ceiling, not a cost ceiling — and is the trigger for the GCP
migration already documented in §13, not a new one.**

**What the pessimism should actually target — not costs:**
1. **"Every user pays" is the least realistic part of the question, not the costs.** §3's
   economics table assumes ~3% conversion at $5; even a generous 6% conversion is nowhere
   near 100%. The infra math above holds at any conversion rate — it's revenue-per-payer,
   not revenue-per-registered-user, that funds the fixed costs.
2. **TAM ceiling for a single niche.** US infra/DevOps/SRE is a bounded population (order
   of magnitude: hundreds of thousands, not tens of millions) [ASSUMPTION — not sized this
   session]. "Every user" pursued to 50k–100k *concurrent paying subscribers* in one niche
   implausible without multi-niche expansion, which is exactly what the "multi-niche" cost
   band above assumes.
3. **Churn is structural, not incidental.** Job seekers unsubscribe when hired — candidate
   revenue is a flow that needs constant top-of-funnel replacement, not a stock. That makes
   **CAC vs. LTV** the real unit-economics question, not hosting bills: at $6/mo and a
   pessimistic 2–3 month average subscribed lifetime, LTV ≈ $12–18/payer. If acquisition
   (content, ads, communities) costs more than that per payer, growth loses money even
   though hosting margins are ~88%. This is the actual risk already tracked by the kill
   criteria in §6 and the #1 distribution risk in §16 — infra was never it.

**Bottom line:** yes, comes out ahead, by a wide margin, at any realistic scale — the
$6/mo price point was never the fragile part of this plan. The fragile part is acquiring
and retaining enough payers in a bounded niche, which is a distribution/retention problem,
not a server-cost problem.

---

## 4. Beachhead Market (decision — Revision 4, 2026-08-28)

**Decision: US-wide job seekers, user-driven role targeting.** The shared job corpus
grows from each user's `target_titles` (registered as global search terms on
onboarding). Matching and scoring personalize the deck per user; ingest does not
assume an engineering niche.

Rationale:
- Product intent is "for everyone," not only infra/DevOps/SRE — marketing, onboarding,
  and ingest must align.
- User-driven terms keep API spend bounded (plan §8): new titles trigger a
  quota-budgeted `term_ingest`; the daily cron rotates through active terms.
- Per-user hard constraints (salary, commute, remote openness) filter the shared
  corpus at queue-build time.
- Tier-2 ATS boards in `seeds/companies.yaml` remain a supplementary tech-heavy
  source until employer-direct posting (Phase 6).

US-only at launch still applies (§12). Do not ingest "everything" in one query — breadth
comes from accumulated user target titles, not a static mega-term list.

---

## 5. Product Definition — V1 ("Swipe Deck + Apply To-Do") — Revision 3

V1 in one sentence: **User uploads a resume and sets constraints once; the system
backfills a queue with the last 4 weeks of matching jobs; the user swipes through the
deck — Interested / Not interested — which trains their preference model AND builds
their Apply To-Do list; every day the newly posted matches are appended to their queue.**

### Research verdict on "Tinder for jobs" (owner asked)
- [FACT, prior reporting — not re-verified today] Swipe-first job apps have existed:
  Jobr (acquired by Monster, 2016), Switch (faded out), and card-style mobile UIs on
  Indeed/ZipRecruiter. Swipe as a *gimmick* did not win — those apps paired swiping
  with instant low-quality applications and died of low signal on both sides.
- **Our version is different in the two ways that matter, so the verdict is GO:**
  1. The swipe is a **labeling action, not an application**. Left/right taps are
     exactly the high-volume, low-friction training data the preference engine (§10)
     needs — the 4-week backfill means a new user can generate 100–300 labeled examples
     in their first few sessions, which solves the cold-start problem that kills most
     recommenders. This is the strongest argument FOR the swipe UX. [ASSUMPTION on
     volumes; measure in Phase 2]
  2. Applying stays **deliberate**: right-swipes land on a To-Do list the user works
     through on purpose. No swipe-to-apply spam — that failure mode (and the employer
     backlash to it) is what killed the genre and what §12 already prohibits.
- Guardrails so swiping stays honest signal: cards must still show the §5 card contract
  (salary, location, why-bullets) so swipes are informed; skip ≠ reject; rapid-fire
  identical-direction streaks get decayed weight (mindless-swiping guard, §10).

### The queue model (core mechanic — binding)
1. **Backfill on signup:** after onboarding, build the user's queue from all corpus
   jobs posted in the trailing **28 days** that pass their hard constraints, ordered by
   score (interleaved with explore picks, §10). Backfill comes from the SHARED corpus
   (§8) — per-user API calls only if the user's search terms aren't already covered by
   the global term set (one-time, quota-budgeted; the term then joins the global set).
2. **Daily top-up:** each night, jobs first seen that day which match the user land at
   the front of their queue (capped at ~30/day by score so the queue never becomes an
   infinite guilt pile; cap in `scoring_config`).
3. **Queue hygiene:** unswiped cards auto-expire when the job closes or passes 28 days
   old; expired cards are recorded as `expired_unswiped` (weak signal, §10).

### In scope (v1)
1. Auth: email magic-link login. No passwords, no OAuth providers in v1.
2. Onboarding (resume-first — owner directive): **resume upload (PDF/DOCX) → local LLM
   extraction → user confirms/edits parsed profile** → short questionnaire: target
   titles/search terms (free text + suggestions), min salary, locations + radius,
   remote/hybrid/onsite acceptability, industries to avoid, free-text "what I actually
   want." Extracted facts carry `confirmed|inferred|needs_confirmation` status (§18)
   and inferences are never silently promoted to facts.
3. Ingestion pipeline: scheduled pulls from sources in §8 → normalize → dedupe → store
   into the shared corpus (28-day rolling active window).
4. Queue builder: backfill + daily top-up per the queue model above.
5. **Swipe deck (primary UX):** one card at a time, keyboard/touch/click. Actions:
   - **Right / Interested** → preference signal + job added to Apply To-Do.
   - **Left / Not interested** → preference signal; optional one-tap reason chips
     (`not qualified` | `overqualified` | `comp too low` | `location/remote` |
     `don't want this work` | `company`) — skippable to keep swiping fast, but shown
     every time; reasons are the highest-value training signal (§10).
   - **Skip/defer (down)** → card returns later; weak signal.
6. **Apply To-Do list:** statuses `to_apply → applied → archived`. "Apply" opens the
   job's ORIGINAL posting in an **in-app Apply Browser** (ephemeral remote Chromium /
   Playwright streamed into the SPA) when available, with **Open in new tab** as
   fallback (`applied_clicked`). After close (or new-tab fallback), a "did you apply?"
   prompt (`applied_selfreport`). Users may use the **Brain** tool to select page
   content and insert AI-drafted answers into form fields **with explicit confirmation
   per insert** — JobDeck never submits the ATS form unattended. Native in-platform
   applications arrive only with employer-posted jobs (Phase 6).
7. Browse/list view (secondary): the same queue + already-swiped piles as a filterable
   list (remote mode, salary floor, posted-within, distance, keyword) — for users who
   want to search rather than swipe; same cards, same actions.
8. Daily email: "N new jobs in your queue" + top 3 cards, deep-linking into the deck.
9. Metrics/event log for everything (§11).
10. Admin page: per-user match quality inspection, source health, prompt versions,
    API-quota consumption (JSearch/Adzuna budgets — §8).

### Explicitly OUT of scope for v1 (agents must not build these)
Employer accounts (Phase 6); native in-platform applications; **unattended** auto-apply
or multi-step form submission without the user present; CAPTCHA solving; LinkedIn login
automation; messaging; mobile apps (the web deck must be mobile-responsive — that's
not a native app); skill verification; collaborative filtering; social features;
multi-region; payments (until Phase 3); public SEO job pages (Phase 4; also check
aggregator ToS on republishing first — JSearch/Adzuna data is licensed for our app, not
necessarily for public republication); scraping Indeed/LinkedIn/Glassdoor directly
(never); n8n anything (§18).

**Allowed with human-in-the-loop:** assisted fill of third-party apply forms via Apply
Browser (select → draft from profile → user-approved insert). Unattended submit remains
forbidden in every phase without ⚖️ review (§17).

### Match card format (contract for deck + list + email)
```
[87% match]  Senior Platform Engineer — Acme Corp
$140–170k · Remote (US) · posted 1d ago · via Adzuna
Why: strong Kubernetes/Terraform overlap · matches your $140k+ target ·
remote matches your preference · progression from SRE toward platform work
Caution: wants Go experience — you listed Python primarily
[← Not interested]   [↓ Skip]   [Interested →]
```
Every card MUST show: score, salary (or "salary not listed" — never invent one), work
mode, age of posting, source, 2–4 "why" bullets, 0–2 honest "caution" bullets, and an
expandable full description with a direct link to the employer's own posting page.
Honesty about weak matches is the trust moat — informed swipes are the whole point.

---

## 6. Validation Plan & Kill Criteria

### Phase 0 — Setup research spike (≤1 week)
Verify Tier-1 API volume/quality per E0.1 (§14): run the niche search-term set against
Adzuna + JSearch + Remotive for 3 days. **Gate: ≥300 unique relevant niche jobs/day,
salary present on ≥40% of them, and JSearch burn fits the $25/mo tier.** If the volume
or quality isn't there, fix the term set or add Tier-2 sources before writing product
code. **Gate to Phase 1.**

### Phase 1 — Concierge (2–3 weeks, throwaway Python scripts — NO n8n)
Recruit 10–20 people (wife, friends, r/devops volunteers). Collect their profile via a
form. Owner runs ad-hoc Python scripts (reusing E0 spike code + Ollama) to pull, score,
and email each participant a daily list of matches for 2 weeks. Track reactions in a
spreadsheet.
- **Pass:** ≥60% of participants open ≥4 digests/week in week 2 AND ≥25% of
  recommendations get "Interested." [ASSUMPTION-based thresholds; treat as directional]
- **Kill:** <30% still engaging in week 2, or a majority say "this is no better than my
  LinkedIn alerts." Stop; the product premise is wrong regardless of tech.

### Phase 2 — V1 build + closed beta (Months 1–3)
Build §5. 30–100 users. Measure (event-sourced, §11): activation (completed ≥50
backfill swipes in week 1), swipes/session, right-swipe rate trend, reason-chip usage,
queue completion rate, To-Do → applied conversion, D7/D30 return rate.
- **Pass:** ≥50% of signups activate; week-4 retention (swiped in week 4) ≥30% of
  activated users; right-swipe precision improving (user's right-swipe rate on the
  model's top-decile cards rises over their first 200 swipes).
- **Kill:** week-4 retention <15% after two full tuning cycles → users don't want it.
- **Swipe-specific kill:** if users swipe heavily but <10% of right-swipes ever reach
  `applied_clicked` by week 4, the deck is entertainment, not a job tool — rework the
  To-Do/apply loop before growing.

### Phase 3 — Willingness to pay (Months 4–5)
Sean Ellis test ("how disappointed if this went away") + a real Stripe paywall on Pro.
- **Pass:** ≥40% "very disappointed" among weekly-active; ≥5% of active free users
  convert at $5/mo within 30 days of paywall launch. (At $3–6 pricing this gate
  measures product love, not income — the income gate is Phase 6 employer revenue.)
- **Kill:** <2% conversion AND <25% "very disappointed" → keep as free portfolio
  project or shut down; do NOT invest more months chasing income replacement.

### Phase 4+ gates
Growth (Phase 4) requires Phase 3 pass. Application-assist (Phase 5) requires ≥500 WAU.
Employer side (Phase 6) requires ≥5,000 candidates in niche + legal review (§12).

---

## 7. Growth Strategy (first 100 / 1,000 / 10,000)

- **First 100:** personal network + 3–5 honest "I built this, roast it" posts in
  r/devops, r/sre, Hacker News (Show HN), DevOps Discords. hiring.cafe grew exactly this
  way. [FACT that hiring.cafe runs a Reddit community; ASSUMPTION on causality]
- **First 1,000:** weekly public artifact from your data (e.g., "State of DevOps hiring:
  salary distribution across 40k live infra postings this month") — the data exhaust is
  inherently shareable; referral loop ("give a friend 3 months of Pro"); niche
  newsletters (DevOps'ish, SRE Weekly) sponsorships are cheap [ASSUMPTION].
- **First 10,000:** programmatic SEO on aggregate pages (salary by title/region, tech
  co-occurrence) — NOT on republished job listings (thin/duplicated content + respect
  for sources); YouTube/TikTok "AI found me a $30k raise" user stories; partnerships
  with bootcamps/cert programs (KodeKloud-style audiences) [ASSUMPTION].
- Non-goals: paid ads before Phase 4; press; influencer spend.

---

## 8. Job Data Strategy (decision — legal/technical)

**Core principle: only sources that are public, intended for programmatic/redistributive
use, or explicitly licensed. NEVER scrape Indeed, LinkedIn, Glassdoor, or ZipRecruiter
(ToS violations, litigious owners — [FACT] LinkedIn's hiQ litigation ran for years and
LinkedIn treats scraping as ToS violation).**

**Revision 2 — owner directive: prefer bulk-volume APIs for the first jobs on the
platform.** The owner's existing n8n workflow already proved Adzuna + JSearch
(OpenWebNinja) + Remotive end-to-end. Tiers re-ordered accordingly: aggregator APIs are
now Tier 1 (v1 volume), ATS-direct is Tier 2 (free enrichment/coverage, grows over
time), employer-direct is Tier 3 (becomes the REVENUE source in Phase 6).

| Tier | Source | Mechanism | Cost | Notes |
|---|---|---|---|---|
| 1 | **Adzuna API** | Aggregator REST API (`/v1/api/jobs/us/search`) with app_id/key; supports `what_or`, `salary_min`, `max_days_old`, lat/lon | Free dev tier; paid at scale | [FACT] official developer API for listings + salary data. Already proven in the owner's n8n workflow. Redirect URLs go via Adzuna (affiliate-style links) — fine for v1. |
| 1 | **JSearch (OpenWeb Ninja)** `search-v2` | Aggregates Google-for-Jobs → Indeed/LinkedIn/Glassdoor/ZipRecruiter postings with apply links | [FACT] Free 200 req/mo → **$25/mo 10k req → $75/mo 50k → $150/mo 200k**; also on RapidAPI | [FACT] returns rich pre-extracted fields: `seniority_level`, `required_experience_years`, `required_technologies`, `work_arrangement`, salary, benefits, lat/lon, multiple `apply_options` — this offloads most LLM normalization (§9). ⚠️ Third-party dependency on Google SERP scraping: legally it's THEIR risk surface, but treat as replaceable (adapter isolation) and **verify their ToS re: caching/storage duration** before Phase 4 public pages. Budget queries: ~30 niche search terms/day × pagination ≈ 3–6k req/mo → $25/mo tier. |
| 1 | **Remotive API** | Free JSON API, remote jobs | Free (attribution) | [FACT] proven in owner's workflow; remote-tech coverage. |
| 2 | **Greenhouse Job Board API** | Public JSON per company board (`boards-api.greenhouse.io/v1/boards/{company}/jobs`) | Free | [FACT] documented public API. Use to (a) enrich/dedupe-prefer over aggregator copies, (b) grow free coverage; seed list from companies seen in Tier-1 results. |
| 2 | **Lever / Ashby / SmartRecruiters / Workable** public posting feeds | Public JSON per company | Free | Same adapter pattern; add incrementally — NOT a v1 blocker anymore. |
| 2 | **USAJOBS API** | Official US federal jobs API | Free | [FACT] official; zero risk, low niche relevance. |
| 3 | **Employer direct posting** | Employer accounts post into our schema | **They pay us** | Phase 6. Direct-posted jobs get `is_direct=true`, native apply, and priority (clearly labeled — never fake-boost scores). |
| 3 | Licensed datasets (TheirStack, Coresignal…) | Paid bulk | $hundreds+/mo | Only if Tier 1+2 coverage proves insufficient. |

Implementation rules for agents:
- One `SourceAdapter` interface; each provider is a plugin emitting the **standard job
  schema the n8n workflow already defined** (title, company, location, remote, lat/lon,
  employment_type, salary, date_posted, description, requirements, source, source_url,
  collected_timestamp) — extended with normalized fields per §13. Port, don't reinvent.
- API keys live in the homelab-infra secrets workflow (SOPS/local), NEVER in code or
  n8n exports. Per-source daily quota budgets enforced in the adapter (JSearch
  especially — it's metered money); admin dashboard shows consumption.
- Respect robots.txt and rate limits for Tier-2 board endpoints (≤1 req/sec/host,
  honest User-Agent with contact email, backoff, ETag caching).
- Dedupe: canonical hash on (normalized title, company, location, description simhash).
  Cross-source dedupe prefers Tier 1 (ATS-direct) records.
- Freshness: store `first_seen`, `last_seen`; a job absent from its source for 3
  consecutive crawls is marked closed. Never recommend jobs older than 14 days or
  marked closed — ghost-job avoidance is a headline feature.
- Store the raw payload (JSONB) alongside normalized fields for reprocessing.

---

## 9. AI Strategy & Economics (decision)

**Principle: deterministic code wherever possible; embeddings for semantic similarity;
LLM calls only where language understanding earns its cost. All v1 inference on your
desktop Ollama; the architecture must keep the LLM behind one internal service boundary
so a later swap to GCP Vertex/other APIs is a config change.**

**Hardware reality (Revision 2):** inference runs on the SAME host as the entire
homelab — `thenetwork`, GTX 1660 Super, **6GB VRAM**, Ollama as a host systemd service
on `:11434` (already deployed per homelab-infra). Consequences, all binding:
- **Small models only.** The existing career-coach n8n workflow used `qwen3:14b` with
  `lowVram` + 24k context — that spills to CPU/RAM on a 1660S and is far too slow for
  batch pipelines. Do not repeat this.
- **Decision: `qwen2.5:7b-instruct` (Q4_K_M, ~4.7GB)** for extraction/explanations;
  fallback `llama3.2:3b` if contention demands it. `nomic-embed-text` (~270MB) for
  embeddings. Keep context ≤8k; chunk long descriptions. E0.2 benchmarks confirm.
- **Minimize LLM work structurally:** JSearch `search-v2` already returns
  `seniority_level`, `required_experience_years`, `required_technologies`,
  `work_arrangement`, salary, and benefits [FACT] → JSearch records need **no LLM
  normalization pass** (regex/mapping only). LLM extraction is reserved for Adzuna/
  Remotive/ATS records missing structure, and resumes.
- **Night-shift scheduling:** GPU batch jobs run 01:00–06:00 when the homelab is idle;
  cap Ollama `num_parallel=1`; the pipeline is queued and resumable.

| Task | Method | Model (v1) | When it runs |
|---|---|---|---|
| Resume parsing | LLM → strict JSON schema (validated, retry-on-invalid) | Ollama `qwen2.5:7b-instruct` | Once per resume upload |
| Job normalization — JSearch records | **Deterministic mapping, NO LLM** (fields pre-extracted upstream) | — | Ingest time |
| Job normalization — Adzuna/Remotive/ATS records | LLM → strict JSON; cache by job hash — each job parsed exactly once regardless of user count | `qwen2.5:7b-instruct` | Nightly batch |
| Embeddings (job docs, user profile docs) | Embedding model via Ollama | `nomic-embed-text` (768-dim); store dim in config, don't hardcode | Nightly batch / on profile change |
| Candidate↔job scoring | Deterministic: hard filters + weighted feature score + cosine similarity (§10). **No LLM.** | — | Nightly per user |
| Explanations ("why/caution" bullets) | LLM, ONLY for each user's top ~10/day; template-generated bullets from structured features as the always-available fallback | `qwen2.5:7b-instruct` | Nightly |
| Preference updating | Deterministic math (§10). **No LLM.** | — | On each feedback event |

Cost math [ASSUMPTION]: with JSearch pre-extraction, LLM load drops to ~1–2k
Adzuna/Remotive/ATS jobs/day × ~1.2k tokens ≈ 1–2.5M tokens/day — comfortably a few
night hours on a 1660S at 7B-Q4 speeds. Explanations at 100 users ≈ 1k short
generations/night. If Ollama is unreachable or the night window overruns, the digest
ships with template bullets rather than failing or slipping. This constraint is
mandatory.

GCP migration path (later): swap Ollama base URL for a vLLM pod on GKE with a small
GPU node, or Vertex AI / Gemini Flash-class API for parse+explain. Keep prompts in
versioned files (`/prompts/*.md` with front-matter) so models are swappable and testable.

### Career assistant — v1 foundation and long-term dual-agent vision

**v1 (shipped):** When users declare target job titles (onboarding questionnaire and
Settings), the API loads their confirmed profile, builds a compact snapshot, and returns
5–10 **qualified** and **adjacent** title suggestions via LLM (`title_suggest` prompt)
with deterministic template fallback if Ollama is unavailable. Suggestions appear as
clickable chips; only explicit user selections on form submit register `search_terms` —
never auto-ingest suggested titles.

**Career Advisor chat (v1, shipped):** Bottom-nav **Advisor** tab with a persistent
profile-aware thread (`GET/POST /api/career/messages`, `DELETE` clears thread,
`POST .../messages/stream` for SSE, `career_messages` table, `career_advisor` prompt).
Profile context is nested JSON (`jobdeck.profile.v2`): `career_totals` (total years
across all roles) is separate from `roles[].employment` (per-job dates +
`tenure_years_approx`). Template fallback when Ollama is unavailable. **Deck** has
**Swipe** and **Search** modes; on desktop (`lg+`) the app shell uses a sidebar and
defaults to Search (`/deck/browse`), while mobile keeps swipe-first bottom nav.
Browse/history supports **change decision** on past swipes
(`POST /api/deck/change-decision`) with todo archive/create coupling.

| Actor | Agent role (future) | v1 foundation |
|---|---|---|
| Job seeker | Career counselor: titles, gaps, interview prep, negotiation, market research | Title suggestions + Advisor chat |
| Employer | Hiring advisor: req shaping, candidate shortlists | Phase 6 employer portal (not built) |
| Platform | Match broker: surfaces mutual fit, facilitates intro | Existing scoring + future opt-in visibility |

**Advisor web / market research (shipped):** Career Advisor runs a two-phase
research loop before streaming the reply: JSON planner → SearXNG `web_search` /
JobDeck `corpus_search` / allowlisted `fetch_url` → cited SSE answer. Config:
`SEARXNG_BASE_URL`, `ADVISOR_RESEARCH_ENABLED`. UI shows “Researching…” and source chips.

Design constraints:
1. **Tool, not free-form browsing in the model.** Advisor emits a structured tool
   call (`web_search` / `fetch_url`); the API executes it and re-injects results.
2. **Search backend:** Homelab **SearXNG** (already on thenetwork) as the default
   query surface; optional allowlisted publishers (BLS, state labor sites, major
   job boards' public SEO pages). No scraping LinkedIn.
3. **Scope filters:** Queries must be career/labor-market related; reject
   unrelated or PII-heavy fetches. Cap results (e.g. top 5 snippets, ~2k chars).
4. **Cite sources in plain text** (publisher + URL). If search fails, say so and
   fall back to profile-only advice — never invent "current" market stats.
5. **Privacy:** Do not send full resume text to external search; only short
   title/region query strings derived from prefs + user question.
6. **Streaming:** Keep SSE; tool round-trip happens before or between token
   streams (search → answer).

Ship order: (a) structured profile JSON — done; (b) tool-call schema + SearXNG
client; (c) UI affordance ("Researching…"); (d) optional corpus-first tool that
queries JobDeck's own job index before the open web.

**Phase 6+ building blocks (not in v1):** Advisor tool calls (search corpus,
web market research, explain gap, draft outreach); employer-side mirror agent;
mediated intro workflow with consent on both sides. The real-estate-agent model:
two specialized agents (candidate counselor + employer recruiter) with the
platform as neutral broker — aligned with §3 sequencing (candidate liquidity
before employer revenue).

---

## 10. Preference-Learning System (v1 design — build exactly this, nothing fancier)

**Stage A (v1): interpretable weighted hybrid. No collaborative filtering (needs users
you don't have), no RL/bandits (needs traffic), no fine-tuning (needs data). Revisit
after 10k+ feedback events.**

User model = four layers:
1. **Hard constraints** (from onboarding, user-editable): min salary, geography/remote,
   never-industries, work authorization. Filter, never score. A hard-constraint miss can
   NEVER be recommended; a user complaint about this class of error is a sev-1 bug.
2. **Stated preferences** (onboarding sliders/choices): initial weights.
3. **Learned preferences**: per-facet weight vectors updated by feedback (below).
4. **Taste embedding**: centroid of embeddings of jobs marked Interested (time-decayed),
   minus a scaled centroid of "don't want this kind of work" rejections.

Scoring per (user, job):
```
score = w_sem * cosine(user_taste_vec, job_vec)          # semantic fit
      + w_skill * jaccard(user_skills, job_skills)        # skill overlap
      + w_comp * comp_fit(job_salary, user_target)        # 1.0 at/above target, decays below
      + w_level * seniority_fit(user_level, job_level)
      + w_geo * geo_fit(...)                              # soft part; hard part already filtered
      + facet_boosts                                       # learned per-facet adjustments
```
Initial weights (config, not code): `w_sem=0.35, w_skill=0.25, w_comp=0.15,
w_level=0.15, w_geo=0.10`. All weights and half-lives live in a `scoring_config` table
so tuning requires no deploy.

Feedback → learning rules (Revision 3 — swipe vocabulary):
- Every event stores `(user, job, action, reason?, ts)` forever (append-only). Actions:
  `swipe_right` (interested), `swipe_left` (+ optional reason chip), `skip`,
  `expired_unswiped`, `todo_applied`, `todo_archived`.
- Signal strengths: `todo_applied` > `swipe_right` > `skip`/`expired_unswiped` (weak
  negative-ish) ; `swipe_left`+reason > bare `swipe_left`.
- **Cold-start blend:** until a user has ~20 right-swipes, weight stated preferences +
  skill overlap heavily and ramp `w_sem` (taste vector) in as labels accumulate — the
  4-week backfill deck exists precisely to get past this threshold fast.
- **Mindless-swiping guard:** within a session, long same-direction streaks (>15) decay
  per-event weight; events with card-view dwell <1.5s get half weight. [ASSUMPTION
  thresholds; config, tune in Phase 2]
- **Time decay: exponential, half-life 30 days** on all behavioral signals. This is the
  "career direction changed" requirement: 6-month-old sysadmin swipes fade; last week's
  AI-automation swipes dominate. [ASSUMPTION: 30d half-life; expose as config, tune in
  Phase 2.]
- Reason-chip-specific updates (why the chips exist):
  - `not qualified` → raise the qualification-gap penalty for that skill/seniority
    delta; do NOT reduce interest in the job family (they *wanted* it).
  - `comp too low` → raise effective salary floor estimate (soft), don't touch taste.
  - `location/remote mismatch` → tighten geo weights only.
  - `don't want this kind of work` → strong negative signal into taste vector + facet
    (job-family) penalty.
  - `overqualified` → seniority floor up.
  - `company` → per-company blocklist entry, no model update.
- **Interested (right-swipe)** → positive taste update + facet boosts (family, stack,
  company size, industry, remote-mode).
- Anti-degeneracy guards (all mandatory):
  - **Exploration slot:** ~1 in 10 deck cards is an "explore" pick — high semantic
    similarity but from an under-shown facet — labeled subtly and tracked separately.
    Prevents filter bubbles and gives the model contrast data.
  - Per-employer cap: max 3 deck cards/day from one company; popularity term is capped
    so big-brand jobs can't dominate (popularity bias guard).
  - Weight updates are bounded per event and per day (learning-rate clamp) so one bad
    afternoon can't wreck a profile.
  - Weekly "does this still look right?" profile summary in the digest with one-tap
    corrections (explicit > implicit when they conflict).

---

## 11. Metrics & Event Model (build in v1, not later)

Append-only `events` table (Postgres, partition by month): `event_id, user_id, type,
entity_id, payload jsonb, created_at`. Event types (closed enum, agents must not invent
new ones without adding to this list): `queue_backfilled, queue_topped_up, card_viewed,
swipe_right, swipe_left, skip, expired_unswiped, todo_added, applied_clicked,
applied_selfreport, todo_archived, digest_sent, digest_opened, profile_updated, login,
unsubscribed`.

Dashboard (admin-only, simple server-rendered page): DAU/WAU, activation rate,
swipes/session, right-swipe rate (overall + per-user trend + top-decile precision),
reason-chip mix, queue depth/completion, To-Do→applied conversion, retention cohorts
(weekly), source health (jobs/day per adapter, parse failure rate, API quota burn),
scoring latency.

---

## 12. Trust, Safety, Legal (constraints agents must respect)

Not legal advice; items marked ⚖️ need professional counsel before the phase indicated.

1. **US-only v1.** Block EU signups (checkbox + IP heuristic). Rationale: [FACT] the EU
   AI Act's Annex III lists employment AI — "recruitment or selection... targeted job
   ads, analysing and filtering applications, evaluating candidates" — as HIGH-RISK,
   with high-risk obligations phasing in on a 24-month timeline from entry into force
   (i.e., now live in 2026). A candidate-side recommender arguably differs from
   employer-side selection, but do not litigate that solo. ⚖️ before any EU launch.
2. **Candidate-side only** keeps us outside NYC Local Law 144 (bias audits for automated
   employment decision tools used by employers) and Colorado's AI act obligations aimed
   at consequential employment decisions [ASSUMPTION on scope — ⚖️ verify before
   Phase 6 employer tools; employer-side ranking is the regulated act].
3. **No unattended auto-apply, ever, in any phase without ⚖️ review.** ATS ToS
   generally prohibit automated submission; employers are actively fighting AI
   application floods; it also poisons our own trust position. Application-assist
   (Apply Browser + Brain) = draft answers from the user's profile and insert only
   after explicit user action; the human always clicks submit on the employer's site.
4. **Privacy:** resumes are sensitive PII. TLS everywhere (even homelab ingress);
   Postgres encryption at rest (LUKS on the volume is sufficient for v1); delete-my-data
   endpoint that hard-deletes profile/resume and anonymizes events (keep aggregate
   stats); resume raw files retained max 90 days after account deletion → 0 days
   (immediate); no selling/sharing data, stated plainly in the privacy policy; CCPA
   basics (disclosure + deletion) from day one. ⚖️ privacy policy review before Phase 4
   public growth.
5. **Explainability & honesty:** every score ships with its "why"; never fabricate
   salary or requirements; label explore picks; never present inferred data as employer-
   stated.
6. **Bias:** never use (or let the LLM infer) protected attributes — age, race, gender,
   disability, national origin — in profiles, prompts, or features. Prompt templates
   must include an instruction to ignore such signals in resumes. Quarterly manual audit
   of recommendations across seniority/geo cohorts. ⚖️ + formal audit before any
   employer-facing ranking.
7. **Security:** OWASP basics; magic-link tokens single-use + 15-min expiry; rate-limit
   auth endpoints; no secrets in repo (sealed-secrets or SOPS for k8s); resume upload:
   size limit 5MB, type sniffing, parsed in an isolated worker, never executed/rendered.

---

## 13. Technical Architecture (decisions — v1, Revision 2)

Grounded in the `homelab-infra` repo (buschmjm/homelab-infra): single k3s host
`thenetwork` (localhost); Ollama is a HOST systemd service on `:11434` (already
exposed as ollama.jbuschmann.com via Cloudflare Tunnel); ingress = Traefik + cloudflared
(one hostname change per apply, dry-run first — repo rule); Postgres lives in the
`database` namespace; monitoring = kube-prometheus-stack + Loki (existing); secrets =
SOPS/`secrets/local/` workflow (repo standard); GitHub is the canonical remote with a
read-only Forgejo mirror; SearXNG + Crawl4AI already run in-cluster (reusable later for
career-coach features, §18). Everything else below is decided here to keep agents
unblocked.

### Stack
| Layer | Decision | Rationale / alternative |
|---|---|---|
| Language | **Python 3.12** everywhere server-side | Owner skill; AI ecosystem. |
| API | **FastAPI + Pydantic v2** | Typed contracts double as the schema source of truth. (n8n fully rejected — §18: nothing runs on n8n in any phase.) |
| Workers | Same codebase, **arq** (Redis-less alternative considered; see queue) run as k8s CronJobs + a queue consumer Deployment | One repo, one deployable image. |
| Queue | **Postgres-backed queue (`pgqueuer`-style, or plain `SELECT ... FOR UPDATE SKIP LOCKED` jobs table)** — NOT Redis, NOT Kafka | One less stateful service on the homelab; volumes are tiny (thousands of jobs/day). Add Redis only if/when latency demands it. |
| DB | **Existing homelab PostgreSQL 16+ with `pgvector`** — single database for relational + vectors + queue | Verify `pgvector` installed & version ≥0.7; HNSW index on job embeddings. A dedicated vector DB is explicitly rejected at this scale. |
| Migrations | **Alembic**, linear history, every schema change via migration | Non-negotiable for the GCP move. |
| Frontend | **React + Vite SPA** (TypeScript), Tailwind, served by the API container as static files | The swipe deck is the primary surface: must support touch gestures, keyboard arrows, and buttons; mobile-responsive web (NOT a native app). React chosen for agent familiarity and later product depth. |
| Email | **SMTP abstraction → start with a transactional provider free tier (e.g., Amazon SES or Postmark)**; NEVER raw homelab SMTP (deliverability) | Digest open tracking via redirect links (no pixel-only tracking). |
| LLM access | Internal `inference` module: OpenAI-compatible client pointed at **Ollama on desktop** (`http://<desktop>:11434/v1`) | Single env var swap to vLLM/Vertex later. All calls: timeout 120s, retry ×2, circuit breaker, graceful-degradation path (§9). |
| Auth | Magic link (signed, single-use), session cookie (HttpOnly, Secure, SameSite=Lax) | No password storage. |
| Payments (Phase 3) | Stripe Checkout + customer portal | Don't hand-roll billing. |
| Observability | Structured JSON logs; Prometheus metrics endpoint scraped by the existing kube-prometheus-stack; dashboards in the existing Grafana (monitoring.jbuschmann.com) | Alert on: ingest failures, digest-send failures, Ollama unreachable during the night window, JSearch quota ≥80%. |
| CI | **GitHub Actions, private repo** (decided: GitHub is already the canonical remote per homelab-infra; Forgejo mirror stays read-only) — lint (ruff), typecheck (mypy), tests (pytest), build image | Deploy stays pull-based via the homelab-infra script workflow. |

### Kubernetes layout (thenetwork, per homelab-infra conventions)
- Namespace `jobs-platform`; manifests live in this app repo, deploy manifests copied/
  referenced under `cluster/thenetwork/apps/` per the infra repo's scope rules (app
  source stays OUT of homelab-infra — its own stated anti-pattern).
- `api` Deployment (1 replica is fine on a single node) + Service; public hostname via
  cloudflared config (e.g., `jobs.jbuschmann.com`) — follow the one-hostname-per-apply,
  dry-run-first rule.
- `worker` Deployment (1 replica, queue consumer).
- CronJobs in the GPU night window: `ingest` (01:00), `normalize+embed` (02:30),
  `score` (04:00), `queue-topup` (05:00, ≤30 new cards/user), `daily-email` (06:30 CT
  — owner's tz; per-user tz later), `queue-expiry` + `source-health` (hourly, no GPU).
  Signup backfill runs on-demand via the worker queue, not cron.
- Resource limits are mandatory on every pod (single shared node with Nextcloud,
  ERPNext, monitoring, game servers, etc. — this platform must not starve the box).
- Secrets via the existing SOPS/`secrets/local` workflow; images from the registry the
  homelab already uses.
- Postgres (`database` namespace) and Ollama (host `:11434`, reachable in-cluster at
  `http://localhost:11434`) are external to this app's manifests — endpoint config
  only. Do not deploy new Postgres or Ollama instances.
- **Single-host reality replaces the old "desktop offline" concern:** if `thenetwork`
  is down, everything is down together. The real risks are GPU/CPU contention (→ night
  window + limits) and single-point-of-failure (→ GCP path below, plus existing backup
  runbooks; add the jobs DB to the backup rotation from day one).

### GCP migration plan (documented now, executed later)
1. DB first: Cloud SQL for PostgreSQL (pgvector supported) — pg_dump/logical replication
   cutover; app config is a single `DATABASE_URL` change because of the one-DB rule.
2. Then workloads: same images → GKE Autopilot (or Cloud Run for api; CronJobs → Cloud
   Scheduler + Jobs). 12-factor discipline (all config via env) makes this mechanical.
3. Inference: desktop Ollama keeps working across the move (it's just an HTTP endpoint);
   replace with GPU node pool or managed API when uptime matters.

### Repository layout (agents: create exactly this)
```
job-platform/
  plan.md                  # this file
  api/                     # FastAPI app (routers, deps, auth)
  core/                    # domain: models, scoring, preference engine (pure, tested)
  ingest/                  # SourceAdapter interface + adapters/ (adzuna, jsearch, remotive, greenhouse, lever, usajobs)
  inference/               # LLM + embedding clients, prompt loading, JSON-schema validation
  workers/                 # queue consumer, cron entrypoints
  web/                     # React/Vite frontend
  prompts/                 # versioned prompt files with front-matter (model, version, schema)
  migrations/              # alembic
  deploy/                  # k8s manifests (kustomize base + homelab overlay + gcp overlay stub)
  seeds/companies.yaml     # curated ATS board tokens for the niche
  tests/
```

### Core schema (v1 — agents extend via migrations only)
`users`, `profiles` (parsed resume JSONB + structured columns + per-fact status),
`hard_constraints`, `preference_weights` (per-user facet weights, versioned rows),
`companies`, `jobs` (normalized + `raw jsonb` + `embedding vector(768)` +
`first_seen/last_seen/status`), `job_sources` (provenance),
`user_job_queue` (user, job, score, explain jsonb, slot_type[core|explore], state
[queued|swiped_right|swiped_left|skipped|expired], enqueued_at, swiped_at, reason?),
`todo_items` (user, job, status[to_apply|applied|archived], timestamps),
`search_terms` (global term set + which user contributed them),
`feedback_events`, `events` (§11), `scoring_config`, `digests`, `queue_jobs`.

---

## 14. Phased Roadmap & Agent Work Breakdown

> Rules for implementation agents: (1) work only on tasks for the CURRENT phase;
> (2) every task lands with tests + migration + docs updated; (3) no new dependencies
> beyond this plan without owner sign-off; (4) no feature not listed here; (5) each epic
> below is sized to be a single agent session.

### Phase 0 (Week 0–1) — Feasibility spike (Revision 2)
- E0.0 **Rotate the leaked Adzuna + OpenWebNinja keys**; store new keys via the
  homelab-infra secrets workflow. (Blocking — do first.)
- E0.1 Volume/quality probe on Tier-1 APIs (throwaway Python scripts — no n8n): run the
  niche search-term set against Adzuna + JSearch + Remotive for 3 days **including a
  28-day backfill pull** (Adzuna `max_days_old=28`, JSearch `date_posted=month`);
  measure jobs/day, backfill corpus size, dedupe overlap %, field completeness
  (salary %, remote flag %, structured-fields % from JSearch), and projected JSearch
  request burn including per-new-user backfill cost. **Gate: ≥300 unique relevant niche
  jobs/day, a ≥3,000-job 28-day corpus, and JSearch burn fits the $25/mo tier.**
- E0.2 Ollama bench on the 1660S: parse 50 Adzuna postings + 3 resumes with
  `qwen2.5:7b-instruct` Q4; measure tokens/sec + JSON-validity (target ≥95% after one
  retry) and total night-window fit.

### Phase 1 (Weeks 1–3) — Concierge (throwaway Python scripts — NO n8n)
- E1.1 Reuse E0.1 spike scripts as the ingest tool: pull daily, normalize into the
  standard schema, score against participant profiles, email each participant their
  daily matches. All disposable code in `spikes/` — none of it ships.
- E1.2 Google-form onboarding; owner sends digests manually; spreadsheet tracking.
- **Gate: §6 Phase-1 pass.**

### Phase 2 (Months 1–3) — V1 build
- E2.1 Repo scaffold, CI, k8s manifests, deploy "hello" api to homelab.
- E2.2 Schema + migrations (all §13 tables), pgvector setup.
- E2.3 Ingest framework + **Adzuna + JSearch + Remotive adapters** (standard job schema
  per §18 contract; safety-net re-filtering; recorded-fixture tests; quota budget
  enforcement; 28-day rolling corpus lifecycle).
- E2.4 Greenhouse + Lever + USAJOBS adapters; cross-source dedupe (prefer ATS-direct
  records); freshness lifecycle.
- E2.5 Inference module: prompt files, JSON-schema-validated parse of resumes +
  non-JSearch jobs, embeddings, graceful degradation, circuit breaker, night-window
  scheduling.
- E2.6 Scoring engine (pure functions, heavy unit tests, golden-file cases).
- E2.7 Preference engine (swipe feedback rules, cold-start blend, decay, clamps,
  mindless-swipe guard, explore slot; property tests: no hard-constraint violations
  ever surface).
- E2.8 **Queue builder:** 28-day backfill on signup (corpus-first, budgeted API
  top-off for novel terms), nightly top-up (≤30/day), expiry hygiene.
- E2.9 Auth (magic link) + onboarding flow (resume upload → confirm parse →
  questionnaire) with per-fact confirmation status.
- E2.10 **Swipe deck UI** (touch/keyboard/buttons, reason chips, dwell tracking,
  expandable card detail) + **Apply To-Do list** (statuses, tracked link-out,
  did-you-apply prompt) + browse/list view with filters.
- E2.11 Daily "N new jobs in your queue" email (deep-links into deck).
- E2.12 Events + admin dashboard (incl. API quota) + source-health monitoring.
- E2.13 Privacy: delete-my-data, retention jobs, privacy policy page.
- **Gate: §6 Phase-2 metrics.**

### Phase 3 (Months 4–5) — Monetization test
- E3.1 Stripe integration, Pro entitlements (25 matches/day, deep explanations, alerts).
- E3.2 Pro features themselves; price A/B **$3 vs $6/mo** (owner directive) with $5 as
  the anchor if traffic can't support an A/B.
- Note: at these price points the REAL Phase-3 signal is conversion % and "very
  disappointed" %, not revenue. Employer revenue (Phase 6) is the income plan (§3).
- **Gate: §6 Phase-3 pass → commit to growth; fail → freeze spend.**

### Phase 4 (Months 6–9) — Growth + hardening
- Data-exhaust content pages (aggregate stats only), referral codes, per-tz digests,
  intraday alerts, begin GCP DB migration if user count strains homelab or uptime hurts.

### Phase 5 (Months 9–12) — Application assist (human-in-the-loop only)
- Tailored resume/cover-letter packet per saved job; export; self-reported outcomes.
  ⚖️ review of any deeper ATS integration.

### Phase 6 (Month 12+) — Employer side = the revenue phase (separate go/no-go doc)
- This is now the committed destination, not a maybe (§3). Still gated: talk to 20
  hiring managers/recruiters in the niche BEFORE building anything; entry bar ≥5,000
  niche candidates, Phase 3 passed, counsel engaged (§12 — LL144/Colorado/EU AI Act
  apply the moment we rank candidates for employers).
- Build order when green-lit: employer accounts + self-serve job slots (native apply)
  → opt-in "open to recommendations" candidate pool → explainable ranked-candidate
  view per posted job → sourcing subscription.

### 12-month calendar (part-time realistic)
| Month | Focus |
|---|---|
| 1 | Phase 0 + Phase 1 concierge |
| 2–3 | V1 build (E2.1–E2.7) |
| 4 | V1 finish (E2.8–E2.11), beta launch to concierge cohort + r/devops |
| 5 | Tune matching; grow to 100–300 users |
| 6 | Phase 3 paywall test |
| 7–9 | Growth loops, content, referrals; GCP DB move if needed; 1k-user target |
| 10–12 | Application assist; employer discovery interviews; decide Phase 6 |

---

## 15. Competitive Moat — honest assessment

Real (earnable) moats, in order:
1. **Per-user longitudinal preference data** — switching cost grows with every feedback
   tap; a copycat starts cold. Real but only after months of usage.
2. **Trust brand in the niche** ("the one that doesn't show ghost jobs and tells you
   when you're NOT qualified") — real, slow, fragile.
3. **Niche depth** (curated employer graph, salary intelligence for infra roles) — real
   at small scale; erodes if you generalize.

Not moats (do not let anyone pretend otherwise):
- "We use AI" — everyone does; models are commodities.
- The matching algorithm itself — reproducible in weeks by a funded team.
- Job data — hiring.cafe proves anyone diligent can build the index.
- Network effects — none exist until (unless) the employer side exists.

Why LinkedIn/Indeed won't crush this immediately: their revenue comes from employers and
recruiters; a candidate-agent that reduces applications-per-hire threatens their ad
model (innovator's dilemma). [SPECULATION, but consistent with their product history.]
A well-funded startup (e.g., Jobright) absolutely could — speed + niche love is the only
defense.

---

## 16. Top 10 Risks (probability × impact)

| # | Risk | P | I | Mitigation |
|---|---|---|---|---|
| 1 | Distribution failure — nobody finds it | High | Fatal | Niche communities, concierge start, data-exhaust content; kill criteria enforce honesty |
| 2 | Retention failure — novelty wears off | High | Fatal | Daily-ritual design, explore slot, weekly profile check-in; Phase-2 gate |
| 3 | Crowded market — Jobright/hiring.cafe ship preference learning | Med | High | Speed, niche depth, trust positioning |
| 4 | Willingness-to-pay ≪ assumed | Med | High | Phase-3 gate before any scale spend |
| 5 | Employer side never materializes (two-sided cold start) → stuck with $3–6 candidate revenue that can't replace income | Med | High | Candidate liquidity first; discovery interviews before building; §3 sequencing; kill criteria honesty |
| 6 | JSearch dependency (third-party Google-SERP aggregator: pricing changes, ToS/caching limits, shutdown) | Med | Med-High | Adapter isolation; Adzuna+Remotive+ATS redundancy; grow free Tier-2 coverage continuously to reduce reliance |
| 7 | Recommendation quality plateau (sparse feedback) | Med | High | Concierge tuning, golden-set evals, owner dogfooding |
| 8 | Regulatory drift (AI + employment) — sharpest at Phase 6 employer ranking | Low-Med | High | US-only, candidate-side v1, opt-in recommendation pool, counsel at gates |
| 9 | Single-host homelab (GPU/CPU contention with other services; one box = SPOF; residential ISP) | Med | Med | Night-window GPU scheduling, pod resource limits, queue+retry, backups, documented GCP path |
| 10 | Solo-founder burnout / scope creep | High | High | This plan's phase gates and out-of-scope lists exist precisely for this |

---

## 17. Open Items for the Owner (the only undecided points)

Resolved in Revision 2: ~~git forge~~ (GitHub private + Forgejo mirror, per
homelab-infra), ~~GPU VRAM~~ (1660 Super 6GB → `qwen2.5:7b` Q4, §9), ~~candidate
price~~ ($3–6, anchor $5, §3), ~~primary data sources~~ (Adzuna/JSearch/Remotive, §8).

Still open:
1. **Rotate the leaked Adzuna + OpenWebNinja API keys** (E0.0 — do today).
2. Curate the niche search-term set (the n8n `job_search_terms` data table is the seed)
   and, for Tier 2, a starter company list.
3. Transactional email provider account (SES/Postmark) — needs your billing.
4. ~~Domain/product name~~ — **RESOLVED:** **JobPicks** (`jobpicks.com` to register;
   beta host remains `jobs.jbuschmann.com` until DNS cutover). See §19 and
   `docs/domain-trademark-checklist.md`.
5. Phase 6 employer pricing discovery (interviews) — owner-led, not delegable.

---

## 18. n8n — fully out (Revision 3)

Owner clarification: the two n8n workflow exports were shared **only to show which job
APIs the owner already has working accounts and keys for** (Adzuna, OpenWebNinja/
JSearch, Remotive). **Nothing runs on n8n in any phase** — Phase 1 concierge included.
The entire product, spikes included, is coded (Python/TypeScript per §13).

What the exports still tell us (reference-only; do not import or execute them):
- **Proven API contracts:** working request shapes for Adzuna (`what_or`, `salary_min`,
  `max_days_old`, results paging), JSearch `search-v2` (`query`, `date_posted`,
  `x-api-key` header), Remotive (`search` param) — saves discovery time in E0.1/E2.3.
- **A sane normalized job schema** (title, company, location, remote, lat/lon,
  employment_type, salary, date_posted, description, requirements, source, source_url,
  collected_timestamp) — adopted as the adapter output contract, extended per §13.
- **Pitfalls to fix in the real implementation:** APIs under-filter (keep a safety-net
  re-filter for age/salary/remote); JSearch `job_is_remote` can be `null` (treat as
  unknown, never as onsite); per-source date-filter semantics differ (one freshness
  policy in config); haversine + text-hint fallback works for geo when lat/lon is
  missing (generalized to per-user home location + radius).
- **Career-coach export:** harvest the candidate-profile JSON schema with
  `confirmed|inferred|needs_confirmation` per-fact status and the one-question-at-a-time
  onboarding style into E2.5/E2.9. Its draft→critic→revise loop is 3–5× inference cost
  — not viable on the 1660S and not needed for batch pipelines; revisit only if a paid
  coaching feature ships on cloud inference (Phase 5+).
- ⚠️ Both exports contain live credentials (E0.0 rotation) — also delete the exported
  JSON files from `~/Downloads` once keys are rotated, and disable/remove the live n8n
  workflow so it stops burning JSearch quota once E0.1 scripts take over.

---

## 19. Launch branding & store marketing (JobPicks)

**Product name:** JobPicks  
**Tagline:** Jobs picked for your profile.  
**Positioning:** Ranked job matches + AI advisor + resume builder. Human-in-the-loop apply
(no unattended auto-apply). Niche: US knowledge workers tired of volume-first job boards.

### Naming decision (2026-09-04)

| Candidate | Verdict |
|-----------|---------|
| **JobPicks** | **Selected.** Domains appear open; no App Store / Play exact-name collision. |
| JobMatcher | Rejected — `jobmatcher.app` is a live AI job-matching competitor. |
| CustomJobs | Fallback only — clean but weaker ASO and brand fit. |

Register `jobpicks.com` and `jobpicks.app` before public growth. Beta continues on
`jobs.jbuschmann.com` until DNS and email DKIM cutover.

### Store identifiers (update before Capacitor release)

| Field | Value |
|-------|--------|
| Play app name | `JobPicks: AI Job Match` (30 chars) |
| Bundle / package ID | `com.jbuschmann.jobpicks` |
| Marketing URL | `https://willowriverautomation.com/jobpicks` |
| App URL | `https://jobs.jbuschmann.com` |
| Privacy URL | `https://jobs.jbuschmann.com/privacy` |
| Support email | `privacy@jbuschmann.com` |

### Marketing assets (in repo)

| Asset | Path |
|-------|------|
| **Canonical marketing page** | `willowriverautomation.com/jobpicks` (Netlify, `willow_river_automation` repo) |
| Homelab fallback landing | `api/static/pages/welcome.html` → `GET /welcome` (optional redirect to WRA) |
| Play Store copy (title, descriptions, SEO) | `docs/store-listing/play-store.md` |
| Screenshot & feature graphic guide | `docs/store-listing/screenshot-guide.md` |
| Pre-submit gate | `docs/mobile-launch-checklist.md` |
| Domain / trademark | `docs/domain-trademark-checklist.md` |

### Launch work remaining (not in this doc's scope — track in issues)

1. ~~**Rebrand codebase**~~ — user-facing UI + package IDs done; internal schemas keep `jobdeck.*` prefix.
2. **Register domains** — `jobpicks.com`, `jobpicks.app`.
3. **Android build** — run `npm run android:scaffold` on machine with Android Studio; see `docs/play-store-readiness.md`.
4. **Replace welcome mockups** — swap CSS phone mockups for real screenshots after APK exists.
5. **Play Console** — paste listing from `docs/store-listing/play-store.md`, data safety form.
6. **iOS** — deferred; same listing patterns apply when App Store ships.

### ASO keyword strategy (Play Store)

Google indexes title + short + full description. Primary terms: `job search`, `AI job match`,
`personalized jobs`, `resume builder`, `career advisor`, `swipe jobs`. See full copy in
`docs/store-listing/play-store.md` — do not keyword-stuff; repeat naturally 2–3× in body.
