# Board-sweep ingest + profile-first scoring

**Status:** ready for swarm implementation  
**Repo:** `/home/dad/job-platform`  
**Python:** `/home/dad/job-platform/.venv/bin/python`  
**Tests:** `/home/dad/job-platform/.venv/bin/pytest`  
**Do not deploy** until the auditor package (Package Z) is green.

This document is the only source of truth for this work. If something is not specified here, **do not invent it**. Leave it out or ask the auditor package to flag a gap. Do not scrape Indeed, LinkedIn, Glassdoor, or ZipRecruiter. Do not enable paid JSearch. Do not add a persisted scores table. Do not split profile embeddings into two vectors. Do not change apply-packet / apply-browser code.

---

## 0. What we are building (one paragraph)

Nightly ingest pulls **all jobs it can legally get from free sources**, then keeps only postings with `date_posted` in the last **1 day**. Those rows accumulate in Postgres for **30 days** from `date_posted`, then are closed and deleted. Users are **not** filtered by search-title at ingest time. After import, the existing deterministic scorer ranks jobs against the **user profile** (experience + skills + seniority first; target titles are a small hint). The deck only shows jobs at or above `min_match_score = 0.35`. Scoring still happens at queue-build time (already implemented). We do **not** precompute and store scores.

---

## 1. Locked decisions (do not reinterpret)

| # | Decision | Exact value | Do not |
|---|----------|-------------|--------|
| D1 | Nightly ingest is a **board/feed sweep**, not a title loop | No `for term in terms` on nightly `subset=False` | Keep title-loop as the nightly path |
| D2 | Nightly date filter | `max_days_old = 1` | Use 60 or 28 for nightly sweep |
| D3 | Corpus retention | `API_JOB_MAX_AGE_DAYS = 30` | Keep 60 |
| D4 | After 30 days from `date_posted` | close, then hard-delete via existing retention cron | Soft-close forever |
| D5 | JSearch | Off unless `JSEARCH_ENABLED` is exactly `true` (default off) | Probe or fetch JSearch by default |
| D6 | Adzuna | **Not** in nightly sweep. Still used only by `term_ingest` (`subset=True`) | Add Adzuna to nightly sweep |
| D7 | Remotive | Nightly: one fetch, **empty** `search_terms`, `max_days_old=1` | Search by title nightly |
| D8 | Greenhouse + Lever | Nightly: all seeds in `seeds/companies.yaml`, `max_days_old=1`, empty search terms | Skip boards when no search terms exist |
| D9 | USAJobs | Nightly only if `USAJOBS_API_KEY` is set; no Keyword; `max_days_old=1`; **max 5 pages** | Unbounded paging; require a keyword |
| D10 | Nightly ingest with **zero** search terms | **Must still run** Remotive + boards + USAJobs | Return early / no-op |
| D11 | `term_ingest` | Keep. Still title-based Adzuna+Remotive subset for newly added titles. `max_days_old=1`. No Tier-2. | Delete term_ingest |
| D12 | Freshness lifecycle (`missed_crawls`) | **Do not run** on nightly sweep. Date retention replaces it. | Increment missed_crawls on jobs older than 1 day — that would close the 30-day corpus in 3 nights |
| D13 | Scoring weights (steady state, dataclass + DB) | See §3 | Invent different weights |
| D14 | `min_match_score` | `0.35` for **core** cards; explore cards may go as low as `0.25` | Hard-filter salary/skills/title |
| D15 | No new scores table | Score at queue-build time only (`score_jobs`) | Persist per-user scores |
| D16 | No embedding split | Keep one `profile_prior_embedding` | Create experience/goals embeddings |
| D17 | Hard filters stay as they are today | Blocked companies, work auth, US-only, remote-only when user chose remote-only | Add title or skill hard filters |
| D18 | `QUEUE_EXPIRY_DAYS` | Leave **60** (queue card expiry, not job age) | Change to 30 |
| D19 | `BACKFILL_WINDOW_PREFERRED_DAYS` | Leave **30** | Change |
| D20 | `CORPUS_WINDOW_DAYS` and `BACKFILL_WINDOW_MAX_DAYS` | Both become **30** | Leave at 60 |
| D21 | Paid APIs | Do not add or require any | Upgrade JSearch / paid Adzuna |
| D22 | Latest Alembic revision today | `012` | Create `013` only as specified in Package C/D |

### Critical landmine (read this)

Today `apply_freshness_lifecycle()` closes any open job **not seen in this crawl** after 3 misses. Nightly sweep only fetches jobs posted in the last 1 day, so jobs from days 2–30 would miss every night and be closed on night 3. **Package A must skip `apply_freshness_lifecycle` on nightly (non-subset) ingest.** Retention is `date_posted` only.

---

## 2. Audit of the earlier verbal plan (corrections)

The verbal plan is accepted with these corrections. Implementers must follow the corrections, not the chat.

| Verbal idea | Correction |
|-------------|------------|
| “Score all users at 03:00 into a new store” | **No.** `workers/jobs/score.py` stays a health log + enqueue `cron_queue_topup`. Scoring already runs inside `QueueBuilder.topup_user` / backfill via `score_jobs`. |
| “Pull all US jobs” | **No.** Pull all jobs from **configured free sources** (Remotive feed + GH/Lever boards + optional USAJobs). |
| “Filter by post date then keep forever until we feel like it” | Keep **30 days** from `date_posted`, then close + delete. |
| “Fit scoring imports more jobs” | **No.** Sweep imports. Scoring only ranks. |
| “LLM agents decide fit” | **No.** Deterministic `score_jobs` only. |
| “Disable term_ingest” | **Keep** it for onboarding/settings new titles (Adzuna+Remotive only). |
| Split experience vs goals embeddings | **Out of scope** this swarm. |

---

## 3. Exact scoring config

### 3.1 Dataclass defaults — `core/types.py` `ScoringConfig`

Replace these fields with **exactly**:

```python
w_sem: float = 0.38
w_skill: float = 0.27
w_comp: float = 0.10
w_level: float = 0.15
w_geo: float = 0.05
w_title: float = 0.05

cold_start_w_sem: float = 0.25
cold_start_w_skill: float = 0.40
cold_start_w_title: float = 0.10

min_match_score: float = 0.35
min_explore_score: float = 0.25
```

Leave every other `ScoringConfig` field unchanged (`cold_start_right_swipe_threshold=20`, `daily_topup_cap=30`, `explore_slot_ratio=0.10`, etc.).

`effective_weights()` already renormalizes. Do not change that function except if a test needs the new defaults (Package D).

### 3.2 Weight meaning (do not rebalance)

| Key | Role | Direction |
|-----|------|-----------|
| `w_sem` | Profile embedding vs job embedding (experience-heavy text) | Can they do it |
| `w_skill` | Jaccard skill overlap | Can they do it |
| `w_level` | Seniority stretch (+1 = 0.85, −1 = 0.6) | Both ways |
| `w_comp` | Soft salary (unknown salary already returns 0.35) | Preference |
| `w_geo` | Soft remote/commute | Preference |
| `w_title` | Token overlap with `target_titles` | Preference hint only |

Do not raise `w_title` above 0.05 in steady state.

### 3.3 Deck threshold rules (Package E)

Apply in **both** `build_topup_deck` and `build_backfill_deck` in `core/queue_builder.py`:

1. After hard-constraint filter, drop any `ScoredJob` with `score < config.min_explore_score` (0.25).
2. Split remaining into core vs explore as today.
3. Core list: drop any item with `score < config.min_match_score` (0.35).
4. Explore list: keep items with `score >= config.min_explore_score` (already guaranteed by step 1).
5. Interleave and cap as today.

If `ScoringConfig` is constructed without the new fields (old pickled objects), use `getattr(cfg, "min_match_score", 0.35)` only if you must — prefer adding the fields so getattr is unnecessary.

### 3.4 What stays a hard filter (`core/constraints.py`)

Do **not** edit `passes_hard_constraints` except if a test import breaks. Allowed hard filters remain: closed job, blocked company/industry, min_salary **only when the user set a hard min**, remote-only / local-only openness, commute when required, work authorization, US-only.

Do **not** add: title must match, skill must match, seniority must match, salary must be present.

---

## 4. Current vs target constants

| Location | Today | Target |
|----------|-------|--------|
| `core/job_retention.py` `API_JOB_MAX_AGE_DAYS` | 60 | **30** |
| `core/queue_builder.py` `CORPUS_WINDOW_DAYS` | 60 | **30** |
| `core/queue_builder.py` `BACKFILL_WINDOW_MAX_DAYS` | 60 | **30** |
| `core/queue_builder.py` `BACKFILL_WINDOW_PREFERRED_DAYS` | 30 | **30** (unchanged) |
| `core/queue_builder.py` `QUEUE_EXPIRY_DAYS` | 60 | **60** (unchanged) |
| `ingest/runner.py` nightly `FetchParams.max_days_old` | 60 | **1** |
| `ingest/runner.py` nightly `SafetyNetFilter.max_days_old` | 60 | **1** |
| `ingest/runner.py` `term_ingest` / `subset=True` `max_days_old` | 60 | **1** |
| `ingest/runner.py` `build_tier2_adapters` `max_days_old` | 60 | **1** |
| `ingest/runner.py` early return if no terms | yes | **no** (nightly still runs) |
| `ingest/runner.py` `apply_freshness_lifecycle` on nightly | yes | **do not call** |
| `workers/jobs/retention.py` docstring | “>60 days” | “>30 days” |
| `tests/test_job_retention.py` `test_posted_cutoff_is_60_days` | expects 60 | rename + expect 30 |

Exact cutoff test:

```python
# posted_cutoff_date(reference=date(2026, 8, 28)) == date(2026, 7, 29)
```

---

## 5. Nightly ingest algorithm (Package A — implement exactly)

Replace the body of `pull_all_sources` in `ingest/runner.py` with this behavior. Keep `persist_job`, `close_non_us_open_jobs`, and `close_expired_api_postings`.

```
pull_all_sources(session, search_terms=None, subset=False):

  stats = empty stats dict (same keys as today)

  IF subset is True OR search_terms is not None:
      # term_ingest path — title-based, no boards
      terms = search_terms if provided else ()
      if not terms:
          log and return empty stats  # term_ingest with no terms is still a no-op
      params.max_days_old = 1
      safety_net.max_days_old = 1
      FOR each adapter in build_tier1_adapters(...):  # Adzuna if keys, JSearch only if enabled, Remotive
          FOR each term in terms:
              fetch with search_terms=(term,)
              persist
      do NOT call build_tier2_adapters
      do NOT call apply_freshness_lifecycle
      close_non_us + close_expired_api_postings
      mark_terms_fetched(terms)
      return stats

  ELSE:
      # nightly sweep — NO title loop
      params.max_days_old = 1
      safety_net.max_days_old = 1
      params.search_terms = ()

      Remotive: fetch once with empty search_terms
      IF JSEARCH_ENABLED == "true" AND JSEARCH_API_KEY set:
          skip on nightly (still title-based; do not add a title-less JSearch pull)
      Adzuna: skip on nightly
      FOR each (adapter, board_params) in build_tier2_adapters(...):
          fetch (GH/Lever boards)
      IF USAJOBS_API_KEY set:
          USAJobs: empty Keyword, max_days_old=1, pages 1..5 inclusive
      persist all
      do NOT call apply_freshness_lifecycle
      close_non_us + close_expired_api_postings
      # do not require mark_terms_fetched; if you keep the call, pass ()
      return stats
```

### 5.1 `build_tier1_adapters` changes

```
if ADZUNA_APP_ID and ADZUNA_APP_KEY:
    append AdzunaAdapter
# JSearch:
if os.environ.get("JSEARCH_ENABLED", "").lower() == "true" and os.environ.get("JSEARCH_API_KEY"):
    append JSearchAdapter
else:
    do not instantiate JSearchAdapter
always append RemotiveAdapter
```

### 5.2 Helper you may add

You may add `ingest/sweep_config.py` with **only** these constants (no logic except `jsearch_enabled()`):

```python
NIGHTLY_MAX_DAYS_OLD = 1
USAJOBS_MAX_PAGES = 5
JSEARCH_ENABLED_ENV = "JSEARCH_ENABLED"

def jsearch_enabled() -> bool:
    return os.environ.get("JSEARCH_ENABLED", "").lower() == "true"
```

### 5.3 Tests Package A must add or rewrite

File: `tests/api/test_ingest_user_driven.py`

| Test | Required assertion |
|------|-------------------|
| `test_pull_all_sources_no_terms_runs_sweep` | Replace `test_pull_all_sources_no_terms_is_noop`. With `build_tier1_adapters` mocked to `[]` and `build_tier2_adapters` mocked to one pair, `pull_all_sources(db_session)` (no terms) **must call** the tier2 fetch. `terms_fetched` may be 0. |
| `test_pull_all_sources_fetches_per_term` | Keep. Still used for `subset`/explicit terms. |
| `test_pull_all_sources_subset_skips_tier2` | Keep. |
| `test_nightly_does_not_call_freshness` | Patch `apply_freshness_lifecycle` and assert **not called** on `pull_all_sources(db_session)` with no terms. |
| `test_nightly_skips_adzuna_and_jsearch` | Patch adapters; nightly path must not call Adzuna or JSearch fetch. Remotive and/or tier2 may run. Easiest: spy `build_tier1_adapters` — nightly should still build Remotive-only list (Adzuna keys may be unset in tests). Add a unit test that `build_tier1_adapters` omits JSearch unless `JSEARCH_ENABLED=true`. |

File: `tests/ingest/test_jsearch_enabled.py` (new)

- `jsearch_enabled()` is False when env unset
- `build_tier1_adapters` does not include a JSearch adapter when `JSEARCH_ENABLED` unset even if `JSEARCH_API_KEY=test`

---

## 6. Work packages (swarm)

Each package lists **allowed files**, **forbidden files**, **tests**, and **done when**. An agent may only edit allowed files plus the tests named in that package. If a change requires another file, **stop and record a blocker** — do not silently expand scope.

### Package 0 — Constants and ScoringConfig fields (do this first, ~15 min)

**Owner files (only these):**

- `core/types.py` — add/change fields in §3.1
- `ingest/sweep_config.py` — create as §5.2
- `core/scoring_config_loader.py` — add `min_match_score` and `min_explore_score` to `_NESTED_EXTRACT` **only if** you store them as `{"value": 0.35}`. Prefer storing them as raw JSON numbers (`0.35`) so `_flatten_row` already works (`return {field: value}`).

**Tests:** `tests/test_scoring.py::TestColdStartBlend::test_ramps_semantic_weight` must still pass (w_sem still ramps up; w_skill still ramps down; w_title still higher at 0 swipes than at 20). If it fails because defaults changed, **update numeric expectations only if the inequalities still hold**. If `w0["w_sem"] < w20["w_sem"]` is false with the new numbers, stop — the locked weights must keep that inequality (`cold_start_w_sem=0.25` < `w_sem=0.38` after normalize).

**Done when:** `pytest tests/test_scoring.py -q` passes.

**Forbidden:** ingest runner, queue builder, migrations, yaml seeds.

---

### Package A — Nightly board-sweep ingest

**Depends on:** Package 0 (`ingest/sweep_config.py` may not exist yet — copy constants into runner if Package 0 is not merged; do not invent different numbers).

**Allowed files:**

- `ingest/runner.py`
- `ingest/sweep_config.py` (if Package 0 created it)
- `tests/api/test_ingest_user_driven.py`
- `tests/ingest/test_jsearch_enabled.py`

**Forbidden:** adapters except imports already present; `seeds/companies.yaml`; scoring; queue builder; migrations.

**Must do:**

1. Implement §5 exactly.
2. Nightly does not call `apply_freshness_lifecycle`.
3. Nightly does not loop search terms.
4. `run_ingest()` still calls `pull_all_sources(session)` with no extra kwargs (nightly).
5. `run_term_ingest` still calls `pull_all_sources(session, search_terms=terms, subset=True)`.

**Done when:**

```
.venv/bin/pytest tests/api/test_ingest_user_driven.py tests/ingest/test_jsearch_enabled.py -q
```

all pass, and `rg "apply_freshness_lifecycle" ingest/runner.py` shows the function still defined but **not invoked** from `pull_all_sources`.

---

### Package B — USAJobs on nightly sweep

**Depends on:** Package A (hook in nightly `ELSE` branch). If A is not merged, add `build_usajobs_fetches(quota) -> list[tuple[adapter, params]]` in `ingest/runner.py` and call it from the nightly branch.

**Allowed files:**

- `ingest/runner.py` (USAJobs wiring only)
- `ingest/quota.py` — register `usajobs` budget `daily_limit=50`
- `.env.example` — add empty `USAJOBS_API_KEY=` and `USAJOBS_USER_AGENT=`
- `deploy/secrets/job-platform-secrets.secret.yaml.template` if that file already has Adzuna keys — add the two USAJobs keys as empty placeholders. Do not put real keys.
- `tests/ingest/test_usajobs_runner.py` (new)

**Must do:**

1. If `USAJOBS_API_KEY` missing: skip, log `skipping usajobs adapter: USAJOBS_API_KEY not set`.
2. If set: pages `1` through `USAJOBS_MAX_PAGES` (5). `search_terms=()`. `max_days_old=1`. `results_per_page=100`.
3. Do not add USAJobs to `term_ingest` / subset path.

**Tests:**

- `test_usajobs_skipped_without_key` — unset env, nightly path does not construct `USAJobsAdapter` (patch `__init__` or `build` helper).
- `test_usajobs_fetches_five_pages_when_keyed` — set `USAJOBS_API_KEY=test`, mock fetch to return `[], 0`, assert 5 calls with `page` 1..5 and empty `search_terms`.

**Done when:** those tests pass; `tests/ingest/test_usajobs.py` still passes (do not break the adapter).

**Forbidden:** changing `ingest/adapters/usajobs.py` mapping logic unless a test proves it cannot accept empty Keyword (it already can — `_build_url` omits Keyword when `search_terms` is empty).

---

### Package C — 30-day retention

**Depends on:** none.

**Allowed files:**

- `core/job_retention.py`
- `core/queue_builder.py` — **only** the three constants `CORPUS_WINDOW_DAYS`, `BACKFILL_WINDOW_MAX_DAYS` (and comments). Do not change functions.
- `workers/jobs/retention.py` — docstring only
- `tests/test_job_retention.py`
- `tests/test_queue_builder.py` — only if a test asserts 60-day max window; update expected constant, do not change behavior tests

**Must do:**

1. `API_JOB_MAX_AGE_DAYS = 30`
2. Rename `test_posted_cutoff_is_60_days` → `test_posted_cutoff_is_30_days`
3. Assert `posted_cutoff_date(reference=date(2026, 8, 28)) == date(2026, 7, 29)`
4. `CORPUS_WINDOW_DAYS = 30` and `BACKFILL_WINDOW_MAX_DAYS = 30`
5. Leave `purge_closed_api_jobs` logic as-is (it already uses `API_JOB_MAX_AGE_DAYS`)

**Done when:**

```
.venv/bin/pytest tests/test_job_retention.py tests/test_queue_builder.py -q
```

**Forbidden:** scoring weights, ingest runner.

---

### Package D — Scoring weights + config loader + migration

**Depends on:** Package 0 (fields exist on `ScoringConfig`).

**Allowed files:**

- `core/types.py` (if Package 0 did not land)
- `core/scoring_config_loader.py`
- `migrations/versions/013_scoring_profile_first.py` (new)
- `tests/test_scoring.py`
- `tests/test_scoring_config_loader.py` — create if missing; otherwise update

**Migration 013 rules:**

```
revision = "013"
down_revision = "012"
```

`upgrade()` must:

1. `UPDATE scoring_config SET value = '{"w_sem": 0.38, "w_skill": 0.27, "w_comp": 0.10, "w_level": 0.15, "w_geo": 0.05, "w_title": 0.05}'::jsonb WHERE key = 'score_weights';`
2. Insert (on conflict skip) rows:
   - `min_match_score` value `0.35`
   - `min_explore_score` value `0.25`
   - `cold_start_w_sem` value `0.25`
   - `cold_start_w_skill` value `0.40`
   - `cold_start_w_title` value `0.10`

Use raw JSON numbers, not `{"value": 0.35}`, so the existing flattener works.

`downgrade()` restores `score_weights` to the 001 values (`w_sem` 0.35, `w_skill` 0.25, `w_comp` 0.15, `w_level` 0.15, `w_geo` 0.10`) and deletes the five new keys.

**Loader:** if a test constructs rows with those keys, `load_scoring_config` / `scoring_config_from_db_rows` must populate `ScoringConfig.min_match_score == 0.35`.

**Do not change** `score_job` formula (the weighted sum). Weights change is enough.

**Golden fixtures:** `tests/fixtures/scoring_golden.json` — if `tests/test_scoring.py::TestGoldenCases` fails because scores moved, **update the expected ranges in the fixture** to the new computed scores. Do not loosen assertions to “any float”. Re-run the test, print actual scores, write those into the fixture. If a case `expect_none`, it must still be None (hard constraint).

**Done when:**

```
.venv/bin/pytest tests/test_scoring.py tests/test_matching_quality.py -q
```

If `test_matching_quality` fails only due to score ranges, update those expected ranges the same way. If it fails due to ranking order flipping in a way that a worse experience match outranks a better one, **stop and flag** — do not silently accept a ranking regression.

---

### Package E — Queue min-score filter

**Depends on:** Package 0 (`min_match_score` / `min_explore_score` on `ScoringConfig`).

**Allowed files:**

- `core/queue_builder.py` — `build_topup_deck` and `build_backfill_deck` only (plus a tiny helper `_apply_score_floors` if you want)
- `tests/test_queue_builder.py`

**Must do:** implement §3.3.

**Tests to add** in `tests/test_queue_builder.py`:

1. `test_topup_drops_below_min_match_score` — three `ScoredJob`s with scores 0.50, 0.36, 0.20; config `daily_topup_cap=30`, `min_match_score=0.35`, `min_explore_score=0.25`. Result must include 0.50 and 0.36, exclude 0.20.
2. `test_backfill_core_excludes_below_min_match` — jobs at 0.40 and 0.30; after `build_backfill_deck`, the 0.30 item may appear only if it was placed in explore **and** `>= 0.25`. Assert 0.20 never appears. Easiest path: set `explore_slot_ratio=0` so only core remains; then 0.30 must be excluded and 0.40 included.
3. Existing topup/backfill tests must still pass. If a fixture job scores 0.0 and was previously included, give it `score=0.40` in the test fixture.

**Done when:**

```
.venv/bin/pytest tests/test_queue_builder.py -q
```

**Forbidden:** changing `score_jobs`, constraints, ingest.

---

### Package F — Source health + env docs

**Depends on:** none.

**Allowed files:**

- `workers/jobs/source_health.py`
- `.env.example` — add `JSEARCH_ENABLED=false` (Package B owns USAJobs lines; if you add them too, use empty values only)
- `tests/test_source_health.py` (new if missing)

**Must do:**

1. Do not construct `JSearchAdapter` unless `JSEARCH_ENABLED` is `true` and `JSEARCH_API_KEY` is set.
2. If Adzuna keys missing, skip Adzuna the same way (try/except around constructor is OK).
3. Always probe Remotive.
4. Skip-probe env (`SOURCE_HEALTH_SKIP_PROBE`) source name list becomes `("adzuna", "jsearch", "remotive")` still, or dynamically from what would have been probed. Do not fail if JSearch is skipped.

**Tests:** mock adapters; with `JSEARCH_ENABLED` unset, `JSearchAdapter.__init__` is not called.

**Done when:** pytest for the new/updated source health test passes; `tests` that import source_health still pass.

---

### Package G — Expand `seeds/companies.yaml` (data only)

**Depends on:** none.

**Allowed files:**

- `seeds/companies.yaml`
- `tests/ingest/test_companies_loader.py` (update count if a test hardcodes 10)
- `scripts/verify-ats-boards.py` (new, optional but preferred)

**Must do:**

Keep the existing 10 companies. Append **only** the following extra rows (exact tokens). If you add a `scripts/verify-ats-boards.py`, it GETs `https://boards-api.greenhouse.io/v1/boards/{token}/jobs` or `https://api.lever.co/v0/postings/{slug}?mode=json` with a 10s timeout. **If a token returns non-200, omit that company** and list omissions in the PR/notes. Do not invent replacement companies.

Greenhouse tokens to try:

```
airbnb
coinbase
discord
dropbox
figma
instacart
notion
reddit
robinhood
twilio
doordash
pinterest
box
cloudkitchens
```

Lever slugs to try:

```
netflix
lyft
palantir
twitch
```

YAML format must match existing entries (`name`, `greenhouse` or `lever`, optional `notes`). No other keys.

**Forbidden:** Python ingest logic.

**Done when:** `load_company_seeds()` returns ≥ 10 seeds; every remaining greenhouse/lever token is a non-empty string; file is valid YAML.

---

### Package H — Regression sweep (after A–E)

**Allowed files:** test files only, and only if a failure is caused by an intentional constant change (60→30, noop→sweep). No production code.

**Must run:**

```
cd /home/dad/job-platform
.venv/bin/pytest tests/api/test_ingest_user_driven.py tests/ingest/ tests/test_job_retention.py tests/test_queue_builder.py tests/test_scoring.py tests/test_matching_quality.py tests/test_preference.py tests/api/test_deck_bootstrap.py tests/api/test_search_terms.py -q
```

If `test_deck_bootstrap` / `test_onboarding_enqueues_term_ingest` fail, **do not remove term_ingest**. Fix only if Package A accidentally broke `subset=True`.

**Done when:** that pytest command exits 0.

---

### Package Z — Auditor (after each package, and again at the end)

See §8. Auditor does not write features. Auditor may add a failing test that proves a spec violation, then hand it back.

---

## 7. Swarm launch order

```
Package 0          (blocking)
   ├── A (ingest sweep) ──► B (USAJobs)
   ├── C (retention 30d)
   ├── D (weights + migration)
   ├── E (queue floors)     [needs Package 0 fields]
   ├── F (source health)
   └── G (companies.yaml)
              │
              ▼
         Package H (regression)
              │
              ▼
         Package Z (final audit)
```

Parallel after Package 0: **A, C, D, E, F, G**.  
B waits for A.  
H waits for A, C, D, E.  
Z after H.

### Prompt template for each implementer agent

Copy this and fill `PACKAGE`:

```
You are implementing Package <ID> from
/home/dad/job-platform/docs/board-sweep-scoring-implementation-plan.md
and ONLY that package.

Rules:
- Edit only the Allowed files listed for that package.
- Do not invent features, weights, sources, or tables.
- Do not scrape job boards. Do not enable JSearch.
- If the spec is silent, stop and write BLOCKER: <reason> at the top of your summary.
- Run the Done-when pytest command before you finish.
- Do not deploy. Do not run deploy-on-server.sh.
- Repo is /home/dad/job-platform. Use .venv/bin/pytest.
```

---

## 8. Auditor protocol (Package Z)

A less-capable model can audit by following this checklist **in order**. Every item is a yes/no. Any **NO** is a fail. Do not “fix style” unless it causes a fail.

### 8.1 How to audit

1. `cd /home/dad/job-platform`
2. `git diff` if git exists; otherwise `rg` the files below.
3. Run the commands in §8.3.
4. Fill the checklist. Do not approve with unchecked items.

### 8.2 Grep checks (must match)

Run these exactly:

```bash
# Freshness must not be called from pull_all_sources
rg -n "apply_freshness_lifecycle" ingest/runner.py

# Nightly must not loop terms when subset is false.
# Fail if you still see `for term in terms` used for nightly (subset False) after the ELSE branch.
rg -n "for term in" ingest/runner.py

# JSearch default off
rg -n "JSEARCH_ENABLED" ingest/runner.py workers/jobs/source_health.py

# Retention 30
rg -n "API_JOB_MAX_AGE_DAYS" core/job_retention.py

# Corpus windows
rg -n "CORPUS_WINDOW_DAYS|BACKFILL_WINDOW_MAX_DAYS|QUEUE_EXPIRY_DAYS" core/queue_builder.py

# Weights
rg -n "w_sem|min_match_score|min_explore_score" core/types.py

# No new scores table
rg -n "class JobScore|user_job_scores|predicted_score" core/models.py

# No scraping
rg -n "linkedin.com/jobs|indeed.com|glassdoor.com" ingest/ --glob '!**.pyc'
```

**Pass rules:**

| Check | Pass |
|-------|------|
| `apply_freshness_lifecycle` | Defined, **zero** calls from `pull_all_sources` |
| `for term in` | Only inside the `subset` / explicit-terms branch |
| `JSEARCH_ENABLED` | Present; adapter not built unless env is `true` |
| `API_JOB_MAX_AGE_DAYS` | `= 30` |
| `CORPUS_WINDOW_DAYS` | `= 30` |
| `BACKFILL_WINDOW_MAX_DAYS` | `= 30` |
| `QUEUE_EXPIRY_DAYS` | `= 60` |
| `w_sem` default | `0.38` |
| `w_title` default | `0.05` |
| `min_match_score` | `0.35` |
| `min_explore_score` | `0.25` |
| JobScore / scores table | **no matches** |
| scrape hosts | **no new matches** in ingest adapters |

### 8.3 Commands the auditor must run

```bash
cd /home/dad/job-platform
.venv/bin/pytest tests/api/test_ingest_user_driven.py tests/ingest/test_jsearch_enabled.py tests/ingest/test_usajobs.py tests/test_job_retention.py tests/test_queue_builder.py tests/test_scoring.py tests/test_matching_quality.py tests/test_preference.py -q
```

If Package B added `tests/ingest/test_usajobs_runner.py`, include it.  
If Package F added `tests/test_source_health.py`, include it.

Exit code must be 0.

### 8.4 Behavioral review (read the diff, do not “improve”)

Open `ingest/runner.py` `pull_all_sources`:

- [ ] Zero search terms + `subset=False` still fetches Remotive and/or tier2
- [ ] `subset=True` does **not** call tier2
- [ ] `max_days_old` is 1 in both nightly params and SafetyNetFilter
- [ ] `apply_freshness_lifecycle` not called
- [ ] Adzuna not in nightly branch
- [ ] USAJobs capped at 5 pages

Open `core/queue_builder.py` `build_topup_deck` / `build_backfill_deck`:

- [ ] Scores `< 0.25` never enqueued
- [ ] Core scores `< 0.35` never enqueued
- [ ] Daily cap still applied after floors

Open `migrations/versions/013_scoring_profile_first.py`:

- [ ] `down_revision = "012"`
- [ ] `upgrade` sets the six weights and five new keys
- [ ] `downgrade` deletes new keys and restores old weights

Open `workers/jobs/score.py`:

- [ ] Still only logs counts and enqueues `cron_queue_topup`
- [ ] No new table writes

### 8.5 Issue catalog (if you see X, it is a fail)

| Symptom | Likely cause | Package to bounce |
|---------|--------------|-------------------|
| After 3 deploys, jobs older than 3 days are `closed` | Freshness still running | A |
| Nightly ingest stats all zero when search_terms empty | Early return still present | A |
| JSearch 429s in worker logs | Adapter still constructed | A or F |
| Deck empty for users with good profiles | `min_match_score` applied before scoring, or threshold used 0–100 instead of 0–1 | E |
| Deck full of unrelated jobs (sales vs TPM) | `w_title` raised or `min_match_score` ignored | D or E |
| `test_posted_cutoff_is_60_days` still exists | C incomplete | C |
| Alembic heads diverge | 013 down_revision wrong | D |
| Onboarding no longer enqueues `term_ingest` | A deleted subset path | A |
| USAJobs storms API | paging unbounded | B |
| `companies.yaml` has guessed tokens that 404 | G did not verify | G |

### 8.6 Auditor report format (required)

```
AUDIT Package Z
Date:
pytest: PASS/FAIL
Grep checklist: PASS/FAIL (list any NO)
Behavioral checklist: PASS/FAIL (list any unchecked)
Blockers:
Ship: YES/NO
```

Ship is YES only if pytest PASS and both checklists PASS and blockers empty.

---

## 9. Evaluation after deploy (human or agent with cluster access)

Do **not** do this until Package Z says Ship YES. Then use `./deploy/scripts/deploy-on-server.sh` from `/home/dad/job-platform`.

### 9.1 Ingest evaluation

```bash
kubectl logs -n jobs-platform -l app.kubernetes.io/component=cronjob --tail=50
# or trigger once:
kubectl create job -n jobs-platform ingest-manual --from=cronjob/ingest
kubectl logs -n jobs-platform job/ingest-manual
```

Expect log line `ingest persist complete` with `created` or `updated` > 0 **even if `terms_fetched` is 0**.  
Fail if log says `ingest skipped: no terms to fetch`.

### 9.2 Retention evaluation

```sql
-- posted older than 30 days must not be OPEN
SELECT count(*) FROM jobs
WHERE status = 'open'
  AND is_direct = false
  AND coalesce(date_posted, first_seen::date) < current_date - 30;
-- expect 0 after retention cron
```

### 9.3 Scoring evaluation (manual, Jacob or any onboarded user)

1. Open deck. Cards should show match % (already `score * 100`).
2. Sample 10 cards. Count how many a human would call “same job family as the profile” (not exact title). Target: **≥ 6 / 10**.
3. If < 4 / 10: do **not** raise `w_title`. Lower nothing in code. File a follow-up: dump `components` from `ScoredJob` for those 10 (semantic vs skill vs title). Only then consider raising `min_match_score` to `0.40` in `scoring_config` DB — not in a drive-by code change.
4. If deck has < 5 cards and corpus `open` jobs > 200: `min_match_score` may be too high **or** hard constraints (remote-only) are wiping the set. Check `hard_constraints` for that user before changing weights.

### 9.4 What “good” looks like (do not retune in this swarm)

| Signal | Target |
|--------|--------|
| Nightly ingest completes | yes |
| New rows `date_posted` within 2 days | ≥ 90% of newly created rows |
| Open corpus age | no OPEN API job older than 30 days after retention |
| Right-swipe rate (after a week) | 15–25% on core slots (observe only) |

---

## 10. Out of scope (instant fail if an agent does these)

- Scraping or HTML crawl of Indeed / LinkedIn / Glassdoor / ZipRecruiter
- Enabling JSearch by default or raising JSearch quota
- New SQL tables for scores
- LLM fit classification
- Changing apply packet, apply browser, resume tailor, career advisor
- Changing Auth / Keycloak
- Expanding ingest to Ashby / SmartRecruiters / Workable (future)
- Auto-discovery of ATS board tokens beyond Package G’s fixed list
- Frontend changes (not required; match % already rendered)
- Deploying from a package agent (only after Z)

---

## 11. File ownership map

| File | Packages |
|------|----------|
| `core/types.py` | 0, D |
| `ingest/sweep_config.py` | 0, A |
| `ingest/runner.py` | A, B |
| `ingest/quota.py` | B |
| `core/job_retention.py` | C |
| `core/queue_builder.py` | C (constants), E (two functions) |
| `core/scoring.py` | none (do not edit) |
| `core/scoring_config_loader.py` | 0, D |
| `core/constraints.py` | none |
| `migrations/versions/013_scoring_profile_first.py` | D |
| `workers/jobs/source_health.py` | F |
| `workers/jobs/score.py` | none |
| `workers/jobs/retention.py` | C (docstring) |
| `seeds/companies.yaml` | G |
| `.env.example` | B, F |
| `tests/api/test_ingest_user_driven.py` | A |
| `tests/test_job_retention.py` | C |
| `tests/test_queue_builder.py` | C, E |
| `tests/test_scoring.py` | 0, D |

If two packages touch the same file (`ingest/runner.py` A then B; `core/queue_builder.py` C then E), merge A before B and C before E, or have B/E re-read the file immediately before editing.

---

## 12. Local verification cheat-sheet

```bash
cd /home/dad/job-platform
.venv/bin/pytest tests/api/test_ingest_user_driven.py -q
.venv/bin/pytest tests/ingest/test_jsearch_enabled.py -q
.venv/bin/pytest tests/test_job_retention.py -q
.venv/bin/pytest tests/test_queue_builder.py -q
.venv/bin/pytest tests/test_scoring.py -q
```

Frontend build is not required for this work.

---

## 13. Deploy (only after Package Z Ship YES)

```bash
cd /home/dad/job-platform
./deploy/scripts/deploy-on-server.sh
```

Confirm migrate job applies `013`. Confirm API/worker roll out. Confirm `/health` is ok.

If migrate fails on 013, roll back by not shipping; `downgrade` is defined. Do not hand-edit production `scoring_config` except `min_match_score` later as in §9.3.
