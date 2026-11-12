# Application Packet — Implementation Plan

Streamline job submission: **prepare → confirm → bulk fill → user submits**.

Users review AI-suggested answers on a Prepare screen (use / skip / edit), then open Apply Browser with a confirmed packet bulk-inserted into the form. JobDeck never submits unattended.

**Target:** typical Greenhouse/Lever apply ~40 min → ~8–12 min. Search flow unchanged.

**Non-goals:** unattended submit, CAPTCHA solving, LinkedIn automation, third-party apply APIs (evaluate later).

---

## 1. Architecture overview

```
Swipe right / Tap Apply
        │
        ▼
┌───────────────────┐     background or on-demand
│ Packet generator  │◄──── resume_tailor, apply_assist, career_advisor,
│ (orchestrator)    │      saved_answers vault, job + profile snapshot
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ application_      │  persisted per todo_item (or job_id)
│ packets table     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Prepare UI        │  /todo/:id/prepare — confirm each section
│ (web)             │
└─────────┬─────────┘
          │ "Open application"
          ▼
┌───────────────────┐
│ Apply Browser     │  session carries packet_id
│ + bulk fill       │  scan DOM → match fields → insert confirmed values
└─────────┬─────────┘
          │ user clicks Submit on employer site
          ▼
┌───────────────────┐
│ Self-report         │  existing todo flow
└───────────────────┘
```

**Principle:** Brain becomes a fallback for one-off fields. The default path is packet review + bulk fill.

---

## 2. Data model

### 2.1 `jobs` — apply URL intelligence (Phase 4)

| Column | Type | Notes |
|--------|------|-------|
| `apply_url` | `varchar(2048)` nullable | Direct apply form URL; may equal `source_url` |
| `ats_type` | `varchar(32)` nullable | `greenhouse`, `lever`, `ashby`, `workday`, `unknown` |
| `ats_metadata` | `jsonb` | `{ board_token, posting_id, hosted_url, ... }` |

Migration: `migrations/versions/0XX_job_apply_url.py`

Ingest adapters populate these at normalize time (Greenhouse/Lever tier-2 first; JSearch `apply_options` preserved).

### 2.2 `application_packets`

One active packet per `(user_id, todo_item_id)` or `(user_id, job_id)`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `user_id` | uuid FK | |
| `todo_item_id` | uuid FK nullable | |
| `job_id` | uuid FK | |
| `status` | varchar | `generating`, `ready`, `failed`, `opened`, `applied` |
| `apply_url` | varchar(2048) | resolved URL for browser |
| `ats_type` | varchar(32) | copied from job at generation time |
| `fit_verdict` | varchar(32) nullable | `apply`, `lean_apply`, `lean_skip`, `skip` |
| `fit_rationale` | jsonb | string[] |
| `identity` | jsonb | name, email, phone, links from `resolve_identity()` |
| `resume_draft_id` | uuid FK nullable | tailored `resume_drafts` row |
| `resume_pdf_path` | varchar nullable | server path or object key for attach |
| `cover_letter` | text nullable | |
| `answers` | jsonb | see schema below |
| `generation_error` | text nullable | if `status=failed` |
| `created_at`, `updated_at` | timestamptz | |

**`answers` JSON schema (per item):**

```json
{
  "key": "work_authorization",
  "question_text": "Are you authorized to work in the United States?",
  "suggested_answer": "Yes, I am a US citizen.",
  "source": "vault|profile|llm|user",
  "status": "pending|confirmed|rejected|edited",
  "final_answer": "…",
  "save_to_vault": false
}
```

### 2.3 `saved_application_answers` (Phase 3)

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `user_id` | uuid FK | |
| `question_key` | varchar(128) | normalized slug, e.g. `work_authorization` |
| `question_text` | text | display label |
| `answer` | text | |
| `last_used_at` | timestamptz | |

Unique index on `(user_id, question_key)`.

### 2.4 Events (existing `events` table)

Add kinds: `packet_generated`, `packet_confirmed`, `packet_bulk_fill`, `packet_field_gap`.

---

## 3. API surface

### 3.1 Packet lifecycle

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/todo/{id}/packet` | Start or refresh packet generation |
| `GET` | `/api/todo/{id}/packet` | Fetch current packet (poll while `generating`) |
| `PATCH` | `/api/todo/{id}/packet` | Update confirmed answers, cover letter, resume draft ref |
| `POST` | `/api/todo/{id}/packet/open` | Confirm packet + create apply-browser session with `packet_id` |

Alternative: `POST /api/application-packets` with `todo_item_id` if packets outlive todo UX.

### 3.2 Saved answers (Phase 3)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/application-answers` | List vault |
| `PUT` | `/api/application-answers/{key}` | Upsert |
| `DELETE` | `/api/application-answers/{key}` | Remove |

### 3.3 Apply browser extensions

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/apply-browser/sessions` | Add optional `packet_id`; session stores packet ref |
| `POST` | `/api/apply-browser/sessions/{id}/bulk-fill` | Scan page + insert confirmed packet values |
| `GET` | `/api/apply-browser/sessions/{id}/fill-report` | `{ filled, skipped, gaps[] }` |

`ApplyBrowserCreateRequest` gains: `packet_id: UUID | null`.

### 3.4 Pydantic schemas (`api/schemas.py`)

- `ApplicationPacketAnswer`, `ApplicationPacketResponse`
- `ApplicationPacketUpdateRequest` (patch confirmed items)
- `BulkFillReport`, `BulkFillGap`

---

## 4. Backend services

### 4.1 `api/services/application_packet_service.py` (new)

**`generate_packet(session, user_id, todo_item_id)`**

1. Load todo + job + profile snapshot + identity.
2. Resolve `apply_url` (job.apply_url ?? job.source_url).
3. Set status `generating`; commit.
4. Parallel or sequential:
   - **Fit:** lightweight call to career advisor template or dedicated `fit_verdict` prompt (short JSON).
   - **Resume:** `resume_service.tailor()` for job; export PDF to `resume_pdf_path` (reuse HTML→PDF pipeline from resume export).
   - **Identity:** `resolve_identity()`.
   - **Answers:** `predict_screening_answers()` (see §4.2).
   - **Cover letter:** single `apply_assist_reply()` with job description + “draft 2–3 paragraph cover letter”.
5. Merge vault hits into answers where `question_key` matches.
6. Set status `ready` or `failed`.

Run generation in FastAPI threadpool or background task; client polls `GET …/packet`.

**`update_packet(session, user_id, packet_id, body)`**

- Patch answer statuses, `final_answer`, cover letter.
- Optionally trigger resume re-export if document changed.

**`confirm_and_open(session, user_id, packet_id)`**

- Require at least: identity confirmed, resume present, no required answers still `pending`.
- Create apply-browser session with `packet_id` + `apply_url`.
- Set packet status `opened`.
- Return `ApplyBrowserSessionResponse`.

### 4.2 `inference/application_packet.py` (new)

**`predict_screening_answers(job, profile, identity, vault) -> list[AnswerDraft]`**

- Prompt: given job description + profile, output JSON array of `{ key, question_text, suggested_answer }`.
- Seed list of ~15 common keys (work auth, sponsorship, salary, remote, start date, years exp, why role, etc.).
- Cap at 12 predicted questions per job.
- Map vault entries first; LLM only for gaps.

New prompt file: `prompts/application_packet.md` (strict JSON schema).

**`normalize_question_key(text) -> str`**

- Lowercase, strip punctuation, slug for vault dedup.

### 4.3 `workers/browser_session/` — bulk fill (Phase 2)

**`async def bulk_fill_from_packet(packet, page) -> BulkFillReport`**

1. Enumerate inputs: `input`, `textarea`, `select`, `[contenteditable]`, file inputs.
2. For each field, derive label: associated `<label>`, `aria-label`, placeholder, nearby text.
3. Match to packet values:
   - **Tier 1:** ATS-specific selectors (Greenhouse/Lever field name patterns).
   - **Tier 2:** fuzzy label match (`work authorization` → `work_authorization` key).
   - **Tier 3:** identity field heuristics (`email`, `phone`, `first_name`).
4. Insert only answers with `status in (confirmed, edited)`.
5. For resume file input: upload `resume_pdf_path` via Playwright `set_input_files`.
6. Return report: filled count, gaps (required-looking empty fields), errors.

**Do not click Submit** — product invariant.

### 4.4 `core/apply/ats_detect.py` (new, Phase 4)

```python
def detect_ats(url: str) -> tuple[str, dict]: ...
```

Hostname rules:

| Host pattern | `ats_type` |
|--------------|------------|
| `boards.greenhouse.io`, `job-boards.greenhouse.io` | greenhouse |
| `jobs.lever.co`, `jobs.eu.lever.co` | lever |
| `jobs.ashbyhq.com` | ashby |
| `*.myworkdayjobs.com` | workday |
| else | unknown |

Extract board token + job id from path for GH/Lever.

### 4.5 Ingest changes (Phase 4)

- `ingest/adapters/jsearch.py`: persist best `apply_link` + full `apply_options` in `jobs.raw`; set `apply_url`.
- `ingest/adapters/greenhouse.py`, `lever.py`: set `ats_type`, `ats_metadata`, `apply_url`.
- Dedup: prefer tier-2 direct ATS URL when merging.

---

## 5. Frontend

### 5.1 Routes

| Route | Component | Phase |
|-------|-----------|-------|
| `/todo/:id/prepare` | `ApplicationPreparePage` | 1 |
| `/apply/browser/:sessionId` | `ApplyBrowserPage` (enhanced) | 2 |

**Flow change:** `TodoList.handleApply` → navigate to `/todo/:id/prepare` instead of opening browser immediately.

### 5.2 `ApplicationPreparePage` (new)

Sections (collapsible cards):

1. **Fit check** — verdict badge + rationale bullets (read-only or link to advisor).
2. **Resume** — preview link, “Edit in builder”, confirm toggle; show tailor source.
3. **Contact info** — editable fields from `identity`; confirm all.
4. **Screening answers** — list of `ApplicationPacketAnswer`:
   - Each row: question, textarea (suggested → editable), buttons: **Use** / **Skip** / **Save to vault** (Phase 3).
5. **Cover letter** — textarea + Use / Skip.

Sticky footer:

- **Open application** (primary) — disabled until required sections confirmed.
- **Refresh suggestions** — re-run `POST …/packet`.

Poll `GET …/packet` every 2s while `status === 'generating'`.

### 5.3 `ApplyBrowserPage` enhancements (Phase 2)

On session start with `packet_id`:

1. After first frame load, call `POST …/bulk-fill`.
2. Show **Fill report** drawer: green filled / red gaps.
3. AssistPanel demoted to “Fix a field” fallback.
4. Banner: “Review the form and submit yourself — JobDeck won’t submit for you.”

### 5.4 Swipe-right prefetch (Phase 1b, optional)

On `swipe right`, fire `POST /api/todo/{id}/packet` in background so Prepare opens warm.

### 5.5 Types (`web/src/types/index.ts`)

Add `ApplicationPacket`, `ApplicationPacketAnswer`, `BulkFillReport`.

### 5.6 API client (`web/src/api/client.ts`)

```typescript
packet: {
  generate: (todoId) => POST …/packet,
  get: (todoId) => GET …/packet,
  update: (todoId, body) => PATCH …/packet,
  open: (todoId) => POST …/packet/open,
}
```

---

## 6. Phased delivery

### Phase 0 — Spike (3–5 days)

**Goal:** Validate assumptions before building UI.

| Task | Owner | Done when |
|------|-------|-----------|
| Sample 200 ingested jobs: % with direct ATS URL vs redirect | backend | spreadsheet in repo |
| Prototype `predict_screening_answers` on 10 real JDs | inference | pytest + manual review |
| Prototype Playwright field enumeration on 3 GH + 3 Lever URLs | browser | script in `scripts/spike-bulk-fill.py` |
| Measure packet generation latency (tailor + LLM) | backend | p95 < 45s on homelab Ollama |

**Exit:** Go if ≥50% jobs have resolvable ATS apply URLs in tech niche; bulk fill works on ≥4/6 spike URLs.

---

### Phase 1 — Prepare screen + packet generation (2–3 weeks)

**Goal:** User reviews packet before browser; manual apply unchanged but packet is ready to copy.

| # | Task |
|---|------|
| 1.1 | Migration: `application_packets` table |
| 1.2 | `application_packet_service.generate_packet` orchestrating existing services |
| 1.3 | `inference/application_packet.py` + `prompts/application_packet.md` |
| 1.4 | Router: `POST/GET/PATCH /todo/{id}/packet` |
| 1.5 | `ApplicationPreparePage` + wire TodoList Apply button |
| 1.6 | Packet PDF export for resume (wire existing resume HTML→PDF) |
| 1.7 | Copy-to-clipboard per answer (bridge until bulk fill) |
| 1.8 | Tests: `tests/api/test_application_packet.py`, inference unit tests |
| 1.9 | Events: `packet_generated`, `packet_confirmed` |

**Ship criteria:** User can open Prepare, see tailored resume + 5+ suggested answers, edit/confirm, then open browser manually with packet visible for copy-paste.

---

### Phase 2 — Bulk fill in Apply Browser (2–3 weeks)

**Goal:** Confirmed packet auto-inserted into form; user only reviews + submits.

| # | Task |
|---|------|
| 2.1 | `POST …/packet/open` creates session with `packet_id` |
| 2.2 | `bulk_fill_from_packet` in browser worker |
| 2.3 | Greenhouse field mapping module `workers/browser_session/ats/greenhouse.py` |
| 2.4 | Lever field mapping `…/ats/lever.py` |
| 2.5 | Generic fuzzy label matcher `…/ats/generic.py` |
| 2.6 | Resume file upload via Playwright |
| 2.7 | `POST …/bulk-fill` + `FillReport` UI overlay |
| 2.8 | Tests: mocked DOM bulk fill unit tests; integration test with static HTML fixtures |
| 2.9 | Event: `packet_bulk_fill` with filled/gap counts |

**Ship criteria:** On GH/Lever test postings, ≥80% of confirmed text fields filled; user submits manually; gaps clearly shown.

---

### Phase 3 — Saved answers vault (1–2 weeks)

**Goal:** Repeated questions answered once, reused forever.

| # | Task |
|---|------|
| 3.1 | Migration: `saved_application_answers` |
| 3.2 | CRUD API + settings UI (optional `/settings/application-answers`) |
| 3.3 | Vault lookup in `generate_packet` |
| 3.4 | “Save to vault” on Prepare screen when user confirms/edits |
| 3.5 | Auto-save common keys on first confirm (work auth, sponsorship, salary) |
| 3.6 | Tests: vault merge + dedup by `question_key` |

**Ship criteria:** Second application to similar roles shows vault answers pre-confirmed.

---

### Phase 4 — Apply URL intelligence (1–2 weeks)

**Goal:** Browser opens on apply form, not listing; better question prediction.

| # | Task |
|---|------|
| 4.1 | Migration: `jobs.apply_url`, `ats_type`, `ats_metadata` |
| 4.2 | `core/apply/ats_detect.py` + ingest adapter updates |
| 4.3 | JSearch: preserve `apply_options`, pick best direct link |
| 4.4 | Redirect resolver job (follow 302 once at ingest, store final URL) |
| 4.5 | Greenhouse public GET job schema for question list (unauthenticated) — merge into packet answers |
| 4.6 | Backfill script for existing jobs |

**Ship criteria:** `apply_url` populated on ≥70% of active jobs; Prepare uses it for browser open.

---

### Phase 5 — Ashby + polish (1–2 weeks)

| # | Task |
|---|------|
| 5.1 | Ashby bulk-fill adapter |
| 5.2 | Swipe-right background packet prefetch |
| 5.3 | Prepare screen: link to Career Advisor for fit deep-dive |
| 5.4 | Mobile Prepare UX pass (packet review works on phone before browser) |
| 5.5 | Metrics dashboard: packet → open → self-report funnel |

---

### Phase 6 — User-added jobs fast path (1 week)

| # | Task |
|---|------|
| 6.1 | “Add job by URL” → detect ATS → create job + todo + packet |
| 6.2 | Same Prepare flow without ingest |

---

## 7. Testing strategy

| Layer | What |
|-------|------|
| Unit | `predict_screening_answers`, `normalize_question_key`, ATS detect, field label matcher |
| API | packet CRUD, auth, todo ownership, generation failure handling |
| Integration | bulk fill against HTML fixtures per ATS (committed under `tests/fixtures/apply-forms/`) |
| E2E (manual) | 5 real applications on homelab: time from Prepare → submit |
| Quality | extend `scripts/test_advisor_chat_quality.py` pattern for packet answer quality rubric |

**Packet quality rubric (automated checks):**

- No invented employers/dates (regex + profile cross-check).
- Answer length 1–500 words for screening fields.
- Fit verdict present when job description > 200 chars.

---

## 8. Metrics & kill criteria

Track via existing `events` table:

| Metric | Target (8 weeks post Phase 2) |
|--------|-------------------------------|
| `packet_generated` → `packet_confirmed` | ≥60% |
| `packet_confirmed` → `applied_clicked` | ≥70% |
| `applied_clicked` → `applied_selfreport(true)` | ≥40% (baseline from plan.md) |
| Median time Prepare open → self-report true | <15 min (user survey or session timestamps) |
| Bulk fill fields filled / fields detected | ≥75% on GH/Lever |

**Kill / pivot:** If bulk fill <50% field match after Phase 2, invest in URL intelligence (Phase 4) before more ATS adapters.

---

## 9. Security & compliance

- Packet contains PII — same auth as todo; no cross-user access.
- Resume PDFs stored under user-scoped paths; deleted on account delete (privacy router).
- Never store employer API keys; browser fill only.
- User must click Submit on employer site — unchanged product policy.
- Log bulk fill actions; no submission automation in audit trail.

---

## 10. Dependencies & risks

| Risk | Mitigation |
|------|------------|
| Ollama too slow for packet generation | Prefetch on swipe-right; cache packet; show partial UI while sections stream in |
| Apply URL is aggregator redirect | Phase 4 redirect resolver; show warning on Prepare if `ats_type=unknown` |
| Workday login wall | Show honest banner; identity + resume still help; no promise of bulk fill |
| Playwright file upload fails cross-origin | Fallback: download resume button + user upload |
| Field matcher wrong value in wrong field | Never auto-confirm LLM answers; user must tap Use; highlight inserted fields |

---

## 11. File checklist (new / modified)

**New**

- `docs/apply-packet-implementation-plan.md` (this file)
- `migrations/versions/0XX_application_packets.py`
- `migrations/versions/0XX_saved_application_answers.py`
- `migrations/versions/0XX_job_apply_url.py`
- `api/services/application_packet_service.py`
- `api/routers/application_packet.py` (or extend `todo.py`)
- `api/repositories/application_packet_repo.py`
- `api/repositories/saved_answer_repo.py`
- `inference/application_packet.py`
- `prompts/application_packet.md`
- `core/apply/ats_detect.py`
- `workers/browser_session/ats/greenhouse.py`, `lever.py`, `generic.py`
- `workers/browser_session/bulk_fill.py`
- `web/src/pages/ApplicationPrepare.tsx`
- `web/src/components/application-packet/*`
- `tests/api/test_application_packet.py`
- `tests/inference/test_application_packet.py`
- `tests/fixtures/apply-forms/*.html`
- `scripts/spike-bulk-fill.py`

**Modified**

- `api/routers/todo.py` — packet routes or import sub-router
- `api/routers/apply_browser.py` — `packet_id`, bulk-fill endpoint
- `api/schemas.py` — packet + bulk fill types
- `api/services/apply_browser_service.py` — pass packet to session
- `workers/browser_session/__init__.py` — session stores `packet_id`
- `web/src/pages/TodoList.tsx` — navigate to Prepare
- `web/src/pages/ApplyBrowser.tsx` — bulk fill on load
- `web/src/api/client.ts` — packet API
- `ingest/adapters/*.py` — apply_url + ats metadata
- `core/models.py` — new tables + job columns

---

## 12. Suggested implementation order (single engineer)

```
Week 1:   Phase 0 spike + Phase 1.1–1.4 (schema, service, API)
Week 2:   Phase 1.5–1.9 (Prepare UI, tests, ship copy-paste bridge)
Week 3:   Phase 2.1–2.4 (bulk fill core + GH/Lever)
Week 4:   Phase 2.5–2.9 (generic matcher, UI report, ship bulk fill)
Week 5:   Phase 3 (vault)
Week 6:   Phase 4 (apply URL intelligence)
Week 7+:  Phase 5–6 (Ashby, prefetch, user-added jobs)
```

Parallelizable: ingest/URL work (Phase 4) can start during Phase 2 if spike shows URL pain is the top blocker.

---

## 13. Definition of done (whole initiative)

- [ ] Apply button opens Prepare screen, not raw browser
- [ ] Packet includes tailored resume, identity, ≥5 screening answers, cover letter draft
- [ ] User confirms/skips/edits each item before opening browser
- [ ] Bulk fill inserts confirmed values on Greenhouse + Lever
- [ ] Resume PDF attached when file input detected
- [ ] Fill report shows gaps; user submits manually
- [ ] Saved answers reuse on subsequent applications
- [ ] `apply_url` used when available
- [ ] Metrics instrumented; median apply time measured
