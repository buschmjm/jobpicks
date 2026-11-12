# JobDeck — Research Findings & Decisions for Implementation Agent

Version: 2026-09-02 v2.1 — AUDITOR SIGNED OFF; approved for orchestrator handoff
Scope: Answers to the 12 "Logic Gaps" in the JobDeck comprehensive plan, grounded in
live research fetched 2026-09-02. Audited and approved with amendments; deltas
are integrated inline and itemized in AUDITOR AMENDMENTS at the end.

ORCHESTRATOR HANDOFF INSTRUCTIONS (authoritative):
- This brief is the single source of truth; where the master plan conflicts,
  this brief wins.
- WS-0 (vitest in CI + CareerAdvisor.test.tsx fix) BLOCKS WS-4.
- WS-1 creates Stripe products at 999/1499 cents ONLY (no quarterly, no 300/600).
- WS-2 ships the A7 public-path allowlist BEFORE any role-gate merge.
- WS-8 does not start until domain/trademark clearance + .well-known files +
  Cloudflare bot rules are verified from a mobile (Capacitor) user agent.
- App Review demo account: real production Keycloak user with jobs role and
  seeded data; NO auth bypass mechanism (pushback P1 accepted by auditor).

Sources verified live:
- Teal pricing: https://www.tealhq.com/pricing
- Huntr pricing: https://huntr.co/pricing
- RevenueCat State of Subscription Apps 2025: https://www.revenuecat.com/state-of-subscription-apps-2025/
- OpenAI embedding models (Matryoshka / `dimensions` param): https://openai.com/index/new-embedding-models-and-api-updates/
- Apple App Review Guidelines, rev. June 8, 2026: https://developer.apple.com/app-store/review/guidelines/

================================================================================
GAP 1: PRICING — $3/$6 IS SEVERELY UNDERPRICED; KILL THAT A/B TEST
================================================================================

Verified competitor pricing (fetched live 2026-09-02):
- Teal+ (tealhq.com/pricing): $13/WEEK, $29/30 days, $79/90 days.
  Free tier gated by AI credits (10 bullets, 2 summaries, 2 cover letters).
- Huntr Pro (huntr.co/pricing): $40/month, $90/quarter (~$30/mo effective),
  $160/6mo (~$26.67/mo effective). No free trial; free tier = 2 tailored
  resumes, 2 application packets, 100 tracked jobs.

RevenueCat 2025 benchmarks:
- Higher-priced apps convert BETTER: median download→trial 9.8% (high-priced)
  vs 4.3% (low-priced). Price does not suppress conversion in intent-driven
  categories; job search is maximally intent-driven.
- Y1 realized LTV per payer is ~7x higher for high-priced apps
  ($55.21 vs $8.08 median).

DECISIONS:
1. Replace the $3/$6 test with **$9.99 vs $14.99/mo**. Even $14.99 undercuts
   both named competitors by 50-63%. At $3, 50 Pro users = $150 MRR — cloud
   LLM costs are never fundable. At ~$12 blended, 50 users = $600 MRR (the
   plan's Month-6 target at Month-3 effort).
2. Do NOT build an annual plan (revise WS-4.3). Neither Teal nor Huntr offers
   one. Job search ends when the user is hired (median search ~3-6 months);
   annual mismatches the value window and inflates refunds (hard-commitment
   products: 5.8% refund rate vs 3.4% freemium, RevenueCat). Instead add a
   **quarterly plan at ~25-30% discount** ($24.99/quarter vs $9.99/mo) —
   matches both competitors' structure, captures a full search in one charge.
   TIMING (auditor-amended): WS-1 ships monthly-only $9.99 vs $14.99 A/B.
   Quarterly moves to WS-4 after first paying users — billing code today only
   supports two monthly price IDs, and quarterly needs new env vars, checkout
   UI, and webhook period handling. Deferring an interval (unlike a price
   point) creates no grandfathering debt, so this is safe.
3. Keep referral 90-day Pro — at $9.99 that is a $30 perceived value; much
   stronger share copy.

================================================================================
GAP 2: iOS BILLING — BETTER NEWS THAN THE PLAN ASSUMES (VERIFIED)
================================================================================

Apple guideline 3.1.1(a), current text verified 2026-09-02:
"These entitlements are not required for developers to include buttons,
external links, or other calls to action in their United States storefront
apps." This is the durable result of the Epic v. Apple contempt ruling
(Apr 30, 2025): US-storefront apps may link directly to external purchase
(your Stripe checkout) with NO entitlement and NO Apple commission.

STRATEGY (WS-8.6):
- v1: NO IAP at all. In the US storefront, the upgrade CTA opens Stripe
  Checkout via @capacitor/browser. Explicitly compliant today.
- Non-US storefronts: guideline 3.1.3 still bans in-app purchase CTAs. Gate
  the upgrade button by storefront/region (hide it; rely on 3.1.3(b)
  Multiplatform Services — Pro purchased on web works in the app).
- If IAP is ever added: enroll in the App Store Small Business Program
  (15% commission, not 30%) — qualification is guaranteed well past $1M/yr.
- Legal caveat to encode: the external-link freedom is injunction-based and
  US-only. Keep the region gate CONFIGURABLE so a policy reversal is a config
  change, not an app-store release.

================================================================================
GAP 3: CAC/LTV MODEL FOR SOLO-DEV LAUNCH
================================================================================

- Expected LTV at $9.99/mo: job-search monthly retention will look like
  RevenueCat's worst cohorts BY DESIGN (users churn when hired). Assume 3-4
  paid months → LTV ≈ $30-40, plus quarterly plans pulling revenue forward.
- iOS paid CPI in North America runs several dollars (top-quartile categories
  $14+). With $30-40 LTV and an unproven funnel, paid acquisition is
  unaffordable at launch. CAC target: ~$0 (organic only).
- Channel order (aligns with WS-11.5):
  1. Reddit — RevenueCat 2025 specifically flags Reddit as an undervalued
     install channel. r/jobsearchhacks, r/resumes, r/careerguidance allow
     tool posts if genuinely useful.
  2. Show HN.
  3. Product Hunt after ~2 weeks of beta polish.
  4. Short-form video of the swipe deck (the deck IS the demo).
- Reality check: only ~20% of new subscription apps reach $1,000 TOTAL revenue
  in 2 years; median time to first $1k is 60 days for those that do. Month-1
  target of 10 payers at ~$10 = $100 MRR is realistic and already top-half.

================================================================================
GAP 4: EMBEDDING DIMENSION MIGRATION — MOSTLY AVOIDABLE (CONFIRMED)
================================================================================

OpenAI text-embedding-3-small and -3-large natively support the `dimensions`
API parameter (Matryoshka Representation Learning — confirmed on OpenAI's
official announcement). Set dimensions=768 and the pgvector schema, indexes,
and EMBEDDING_DIMENSION stay untouched. MTEB loss from truncating 3-small
1536→768 is roughly a point — negligible for deck ranking.

CORRECTION TO THE PLAN'S FRAMING: the schema migration is avoidable; the
RE-EMBED IS NOT. Vectors from nomic-embed-text and text-embedding-3-small
live in different spaces — they cannot be mixed in one similarity search.

Cutover plan (WS-9):
1. Add an `embedding_model` column (or a second vector column).
2. Batch re-embed the corpus at dimensions=768. Cost: $0.02/1M tokens ≈
   single-digit dollars for a typical job corpus.
3. Flip reads atomically; drop old vectors.
Zero schema change, one backfill job.

================================================================================
GAP 5: OAUTH2-PROXY VS IN-APP ROLE GATE — IN-APP GATE, UNAMBIGUOUSLY
================================================================================

- oauth2-proxy is a perimeter tool: it blocks EVERYTHING, including the public
  landing page, /privacy, Stripe webhooks, and the .well-known files
  (apple-app-site-association, assetlinks.json) which MUST be publicly
  fetchable anonymously for WS-8 Universal/App Links. oauth2-proxy in front
  would silently break mobile auth.
- The in-app gate (WS-2.1: read realm_access.roles from the already-validated
  JWT in get_current_user) is ~20 lines, unit-testable, per-endpoint.
- Make it a flag: REQUIRE_JOBS_ROLE=true for closed beta, flip to false
  (open registration) at public launch with no infra change.
- Verdict: in-app role gate for the product; oauth2-proxy only as an extra
  wall around /admin or Grafana if desired. Sync the homelab-infra runbook to
  state the in-app gate is authoritative.

================================================================================
GAP 6: GDPR/CCPA GAPS BEYOND DELETE-MY-DATA
================================================================================

Priority-ordered for WS-2.4:
1. Data export (Art. 15/20) — delete exists but access/portability doesn't.
   Add GET /api/privacy/export returning profile, resume text, swipes, and
   applications as JSON. Small endpoint; legally required on request anyway.
2. Retention schedule in the policy — state concrete periods (account data
   until deletion; llm_call_logs and event telemetry 90 days; Stripe records
   7 years for tax). Currently unstated = non-compliant policy.
3. Sub-processor list — Stripe, SMTP provider, Cloudflare (tunnel sees
   traffic), hosting. Resume content flowing to a cloud LLM later is a
   MATERIAL policy change — pre-write the clause now ("resume content may be
   processed by AI providers acting as processors").
4. Lawful basis + consent record for marketing email — digest/alerts need an
   opt-in record and working unsubscribe (WS-5.3 covers the mechanics).
5. CCPA: thresholds ($25M revenue / 100k CA consumers) won't be met for a
   long time, but add a "we do not sell personal information" line.
6. Resume data is not GDPR "special category" per se, but treat it as
   high-sensitivity (it can contain anything the user typed). Encrypt at rest
   on the vault path if not already.

================================================================================
GAP 7: APP STORE REVIEW RISKS (SPECIFIC TO THIS APP, CURRENT GUIDELINES)
================================================================================

- Guideline 4.2 Minimum Functionality — the #1 rejection risk for Capacitor
  wrappers ("repackaged website"). Mitigations for mobile v1 (auditor-amended
  ordering): bundled assets (not remote URL), native tab bar (done),
  splash/icons, optional Capacitor haptics, no visible browser chrome.
  Push notifications (APNs/FCM/device tokens/backend) are the strongest 4.2
  answer but are v1.1 scope — add them if Apple rejects; do NOT block WS-8.
- 5.1.1(v) Account deletion must be IN-APP — the GDPR endpoint exists;
  surface a "Delete account" button in Settings inside the app build. Hard
  requirement, commonly missed.
- 4.8 Login Services — Keycloak first-party username/password is exempt
  ("your company's own account setup"). BUT if Keycloak ever federates
  Google/GitHub login, an equivalent privacy-preserving option (effectively
  Sign in with Apple) becomes mandatory. Flag in the Keycloak bootstrap docs.
- AI content (1.2 / 2.3.1) — cover letters and screening answers are
  user-initiated generated content. Add an in-app disclaimer ("AI-generated,
  review before sending") and describe AI features explicitly in App Review
  notes. The June 2026 guidelines also require disclosing third-party AI
  sharing in the privacy policy (5.1.2(i)) — covered by Gap 6 item 3.
- Job listing accuracy (2.3.1) — add "listings sourced from third parties;
  may be expired" fine print to job cards or footer.
- 2.1 Completeness — provide a working demo account (pre-seeded resume +
  deck) in review notes; a reviewer on a blank Keycloak-gated app is an
  instant rejection.

================================================================================
GAP 8: ARE PRO FEATURES COMPELLING ENOUGH? PARTIALLY — ADD THESE
================================================================================

Current Pro (25 cards, 4 bullets, breakdown, alerts) is a QUANTITY upsell.
Competitors sell OUTCOME upsells. All three below reuse existing LLM plumbing:

1. Unlimited AI application packets; free tier gets 2 TOTAL (lifetime, not
   per day). This is exactly Huntr's free/paid line ("2 Application Packets"
   free) and their headline Pro feature. Highest-ROI change in the plan.
   SCOPE (auditor-corrected): NOT a config toggle. No packet entitlement
   exists today — application_packet_service.py generates for any
   authenticated user. Needs: lifetime counter on users/usage table, gate in
   the generate API, upgrade UX on the prepare page at limit, entitlement
   tests. Estimate ~1-2 agent-days. Still P1.
2. Per-job resume tailoring export — "Tailor for this job → download PDF"
   from the prepare page, Pro-only. Both Teal and Huntr lead their pricing
   pages with this. SCOPE (auditor-corrected): PDF export is NOT built
   (html2pdf.js is in package.json but unused). Scope as WS-4.2 work or
   defer to v1.1.
3. AI interview prep — likely interview questions + suggested answers from
   job posting + resume. Differentiating at $9.99 vs competitors' $29-40.
   TIMING (auditor-amended): v1.1. Needs route, UI, entitlements, prompt,
   and eval — not launch-critical.

================================================================================
GAP 9: CHURN PREVENTION PLAYBOOK (JOB-SEARCH-SPECIFIC)
================================================================================

Accept structural churn (users get hired) and monetize around it:
- "I got hired" exit flow instead of a plain cancel: congratulate, ask which
  job (testimonial + feature attribution = marketing gold), offer a dormant
  "career check-in" free mode. Converts churn into social proof.
- Cancel-flow save offer: one month at 50% or downgrade-to-quarterly.
  RevenueCat: monthly churners reactivate at the highest rate (>13%) — a
  90-day win-back email ("new roles matching your profile this week: N")
  should be WS-5.6, promoted from optional to v1.1-committed.
- The digest email is the retention engine — RevenueCat's top-cited churn
  reason is "not enough usage." The daily digest with 3 high-match cards is
  the usage driver; prioritize deliverability (SPF/DKIM/DMARC on the product
  domain) in WS-1.2.
- First-week activation gate: users who add ≥1 job to the apply queue in
  week 1 are the retained cohort (Ladder's segmentation pattern, RevenueCat
  report). Trigger an email/push nudge if 0 todos by day 3.

================================================================================
GAP 10: PRODUCT DOMAIN
================================================================================

Live registrar availability could not be verified from here — treat these as
candidates to CHECK, not confirmed available. "JobDeck" has name-collision
risk (existing job tools have used similar names).

REQUIRED before committing: USPTO TESS search + app-store search for
"JobDeck" BEFORE fixing the Capacitor appId — com.<owner>.jobdeck is painful
to change after store submission.

Candidates in preference order:
1. jobdeck.app (note: .app TLD enforces HTTPS — fine, the stack is
   HTTPS-only)
2. getjobdeck.com
3. jobdeck.io
4. Fallback rename if the trademark search comes back dirty.

Decision gate: domain + trademark check is the TRUE LONG POLE for WS-8
(Universal Links bake the domain into the shipped binary) — do it this week
even though mobile is P2.

================================================================================
GAP 11: TEST COVERAGE GAPS BLOCKING CONFIDENT MOBILE LAUNCH
================================================================================

Ordered by risk:
1. Stripe webhook contract tests (signature verification,
   checkout.session.completed → tier flip, subscription.deleted → downgrade).
   Money-path, currently ops-unverified.
2. Entitlement boundary tests — free user's 11th card, packet limit,
   role-gate 403s (WS-2 acceptance covers part).
3. Auth callback E2E — token-proxy + PKCE flow; on mobile the Universal Link
   → app-open → token exchange path. Most fragile mobile piece, untestable in
   CI — make it item #1 on the real-device QA checklist (WS-8.8).
4. Playwright mobile-viewport smoke in CI (login stub → deck swipe → add todo
   → open prepare) — catches viewport regressions currently found by hand.
5. Fix CareerAdvisor.test.tsx hoisting + wire vitest into CI (WS-0.3) BEFORE
   WS-4 lands conversion changes, or paywall regressions ship blind.
6. LLM golden-prompt eval (WS-9.5) is correctly placed pre-cloud-cutover;
   not a mobile blocker.

================================================================================
GAP 12: PLAN CORRECTIONS
================================================================================

1. Reprice BEFORE, not after, Stripe wiring: WS-1 creates MONTHLY-ONLY
   $9.99/$14.99 price IDs from day one (quarterly is WS-4, per Gap 1/A1).
   Running the $3/$6 test first anchors early users at an unsustainable price
   and creates grandfathering debt. Revise WS-4.3 "annual plan research" →
   "quarterly plan" (see Gap 1).
2. Move "2-packet free limit" from WS-4 nice-to-have to WS-4 P0 — strongest
   conversion lever (see Gap 8) and it's a counter, not a feature.
3. WS-8 hidden dependency: .well-known/apple-app-site-association and
   assetlinks.json must be served UNAUTHENTICATED from the product domain —
   add explicitly to WS-1.4/WS-7 so the role gate and edge rules never block
   them.
4. Add to WS-2: storefront/region gate for upgrade CTAs in the mobile build
   (Gap 2) — currently in no workstream.
5. Missing micro-workstream: store presence assets — support URL/email and a
   live marketing landing page BEFORE App Store submission (Apple rejects
   placeholder URLs, guideline 2.1). WS-11.4's landing copy has a hard
   deadline: the WS-8 submission date.
6. Freemium expectation-setting for the owner: RevenueCat median freemium
   download→paid at day 35 is 2.18%. Model revenue on 2-3% free→Pro
   conversion, not 10%. (Auditor-amended: treat all RevenueCat figures as
   hypotheses, not planning assumptions. Pessimistic planning model: 1%
   free→Pro, 2-month average paid tenure → LTV ≈ $20-24 at blended pricing.
   This does not change any decision — it strengthens the CAC ≈ $0 mandate.)

================================================================================
AUDITOR AMENDMENTS (v2) — ACCEPTED DELTAS + ONE PUSHBACK
================================================================================

ACCEPTED (integrated inline above where applicable):
A1. Quarterly plan deferred: WS-1 = monthly $9.99/$14.99 only; quarterly in
    WS-4 after first payers. (Gap 1 updated.)
A2. Packet free-limit is ~1-2 agent-days of new entitlement work, not a
    toggle. (Gap 8 updated.)
A3. PDF export not built (html2pdf.js unused) — scope as WS-4.2 or v1.1;
    interview prep is v1.1. (Gap 8 updated.)
A4. Push notifications v1.1; mobile v1 relies on bundled assets + native tab
    bar + splash/icons for guideline 4.2. (Gap 7 updated.)
A5. Referral abuse cap: max 3 successful redemptions per referrer per year,
    plus existing IP/device limits. Assign to WS-2.7/WS-5.
A6. EU/non-US billing documented in WS-8.6: hide in-app upgrade CTA outside
    US storefront; Pro purchased on web must function in-app per guideline
    3.1.3(b) Multiplatform Services.
A7. PUBLIC PATH ALLOWLIST for WS-2 role gate (must never require the jobs
    role — implement as middleware allowlist and TEST each):
      POST /api/billing/webhook
      POST /api/auth/oidc/token
      GET  /api/auth/config
      GET  /api/email/unsubscribe/{token}
      GET  /.well-known/apple-app-site-association
      GET  /.well-known/assetlinks.json
      GET  /health, GET /api/health
      GET  /privacy + static marketing pages
A8. Cloudflare bot-challenge risk: jobs.jbuschmann.com has returned
    cf-mitigated: challenge per the homelab-infra audit. WS-1.4/WS-7 must add
    Cloudflare WAF/bot-rule allowlisting for API + auth callback paths on the
    product domain, and verify from a Capacitor UA before store submission.
A9. Price-variant migration (WS-1): change PRICE_VARIANT_CENTS (300, 600) →
    (999, 1499); update tests/api/test_workstream_b.py and
    tests/test_workstream_b.py which hard-code {300, 600}. Since Stripe was
    never wired in prod, NO ONE has paid at $3/$6 — reset price_variant_cents
    for all users without an active subscription; no grandfathering needed.
A10. WS-0.3 (vitest in CI + CareerAdvisor.test.tsx hoisting fix) is BLOCKING
    for WS-4 conversion work.
A11. Split launch checklists:
    HOMELAB TODAY: Stripe test mode, SMTP optional, REQUIRE_JOBS_ROLE=true,
      no mobile, /metrics token, verify-github-build gate.
    PUBLIC LAUNCH: Stripe live + webhook registered, SPF/DKIM/DMARC
      deliverability verified, privacy export endpoint, Delete-account in
      Settings, accurate privacy policy, product domain + Cloudflare rules,
      REQUIRE_JOBS_ROLE=false (open registration).
A12. "I got hired" exit flow: any testimonial/job-title collection used in
    marketing needs explicit consent copy (Gap 6 overlap). Flow is ADDITIVE
    to the existing Stripe Customer Portal (POST /api/billing/portal): show
    the exit survey in-app first, then hand off to the portal for the actual
    cancellation — do not reimplement cancellation.

PUSHBACK (one item — auditor amendment C is partially wrong):
P1. App Review demo account: agreed on the spec (Keycloak user with jobs
    role, pre-onboarded profile + resume, todos + one generated packet,
    credentials in App Review notes). HOWEVER, the suggestion of a
    REVIEW_DEMO_EMAIL bypass "only in staging, not production" does not work:
    Apple reviewers test the PRODUCTION binary against PRODUCTION backends.
    The demo account must be a real, working production Keycloak user with
    seeded production data — no code-path bypass, no staging-only mechanism.
    Guideline 2.1 alternative if credentials are legally problematic: a
    built-in demo mode pre-approved by Apple, which is more work, not less.

REVISED PRIORITY ORDER (adopted as proposed by auditor):
  P0  Reprice to $9.99/$14.99 before creating Stripe products
  P0  WS-2 role gate + public path allowlist (A7)
  P0  Delete-account button in Settings UI
  P0  Privacy policy rewrite + export endpoint
  P1  2-lifetime-packet free limit (new entitlement work)
  P1  In-context upgrade CTAs (WS-4)
  P1  SMTP + digest deliverability
  P1  Domain + trademark clearance + .well-known + Cloudflare rules
  P2  Capacitor mobile + region-gated billing
  P2  Quarterly plan (after monthly proves out)
  P3  Interview prep, push notifications, PDF export (v1.1)

================================================================================
SIGN-OFF
================================================================================

2026-09-02: Auditor approved v2 for orchestrator handoff. Pushback P1 accepted
(production demo account, no bypass). Gap 12.1 stale "+quarterly" wording
corrected in v2.1 — WS-1 is monthly-only, authoritative. No open items.

================================================================================
END OF RESEARCH BRIEF (v2.1 — AUDITED, SIGNED OFF)
================================================================================
