# Google Play Store listing — JobPicks

Use this document when creating the Play Console listing. Copy is optimized for Play Store
indexing (Google indexes the full description; there is no separate keyword field like iOS).

**Marketing URL (required):** `https://willowriverautomation.com/jobpicks`  
**App host:** `https://jobs.jbuschmann.com`  
**Legacy marketing fallback:** `https://jobs.jbuschmann.com/welcome` (homelab; redirect to WRA after deploy)
**Privacy policy URL:** `https://jobs.jbuschmann.com/privacy`  
**Support email:** `privacy@jbuschmann.com` (or `support@` on product domain once set up)

---

## App identity

| Field | Value |
|-------|--------|
| **App name** (30 chars max) | `JobPicks: AI Job Match` |
| **Package name** | `com.jbuschmann.jobpicks` (update from `jobdeck` before release) |
| **Category** | Business (primary) or Productivity |
| **Tags** (if offered) | Job search, Career, Resume, AI |
| **Content rating** | Everyone / Teen (no mature content; job search) |
| **Target audience** | 18+ job seekers in the United States |

---

## Short description (80 characters max)

```
Swipe AI-ranked job matches picked for your profile. Advisor + resume tools included.
```

Character count: 80

**Alternate (if A/B testing):**

```
Personalized job picks for your skills. Swipe matches, AI advisor, resume builder.
```

---

## Full description (4,000 characters max)

```
JobPicks ranks jobs for your skills and career goals — so you spend less time scrolling and more time applying to roles that actually fit.

SWIPE YOUR PICKS
• Daily deck of ranked job matches with match scores
• See why a role fits before you invest time in an application
• Swipe right to save to your apply to-do list; pass on the rest
• Preferences learn from your feedback over time

AI CAREER ADVISOR
• Ask about pivots, compensation, interview prep, and market trends
• Grounded in your confirmed profile — not generic chatbot advice
• Research-backed answers when you need context beyond your resume

RESUME BUILDER
• Chat to refine bullets, reorder experience, and tailor for each role
• Live preview as you edit
• Stronger applications without starting from a blank page every time

APPLY WITH INTENT
• Right-swipes become a focused apply queue
• Prepare application packets, cover letters, and talking points
• YOU submit every application — JobPicks never auto-applies behind your back

WHY JOBPICKS
Most job apps optimize for volume: more listings, more applications, more noise. JobPicks optimizes for fit. Fewer picks, higher signal, and tools that help you show up prepared.

FREE TO START
• 10 deck matches per day
• AI advisor and resume builder with daily limits
• 2 lifetime application packets

JOBPICKS PRO
Upgrade for more daily matches, unlimited AI tools, full score breakdowns, intraday alerts, and unlimited application packets. Subscriptions billed monthly via Stripe on the web (US storefront).

BUILT FOR US JOB SEEKERS
JobPicks is designed for professionals who want personalized job search — especially in tech and knowledge work — without application spam or unattended auto-apply.

Privacy policy: https://jobs.jbuschmann.com/privacy
Terms: https://jobs.jbuschmann.com/terms
Questions: privacy@jbuschmann.com
```

---

## SEO keyword placement (Play Store)

Google Play ranks on title, short description, and full description. Primary keywords
to weave naturally (do not stuff):

| Priority | Keywords / phrases |
|----------|-------------------|
| High | job search, AI job match, personalized jobs, jobs for me |
| Medium | resume builder, career advisor, swipe jobs, job matcher, apply jobs |
| Long-tail | ranked job matches, job picks, tailored resume, job application helper |

**Rules:**
- Put the strongest keyword in the **app name** (`JobPicks: AI Job Match`).
- Repeat primary terms 2–3× in the full description in natural sentences.
- Avoid competitor names and trademarked terms (LinkedIn, Indeed, etc.) in listing copy.
- Do not claim "#1" or unsubstantiated rankings.

---

## Screenshot plan

Capture on a **real Android device** (not desktop-only). See [screenshot-guide.md](screenshot-guide.md).

| # | Screen | Caption overlay (optional) | Store caption text |
|---|--------|---------------------------|-------------------|
| 1 | Swipe deck with match score | "Jobs picked for you" | Ranked matches with fit scores |
| 2 | Match detail / why it fits | "See why it fits" | Understand the match before you apply |
| 3 | Apply to-do list | "Your apply queue" | Right-swipes become focused to-dos |
| 4 | Career advisor chat | "AI career advisor" | Ask about pivots, comp, and interviews |
| 5 | Resume builder + preview | "Tailor your resume" | Chat to refine bullets for each role |
| 6 | Settings / Pro upgrade | "Free to start" | Upgrade when you need more daily limits |

**Dimensions:** 1080×1920 or 1440×2560 (phone). Minimum 2 screenshots; recommend 6–8.

---

## Feature graphic (1024×500)

**Headline:** `Jobs picked for your profile`  
**Subline:** `Swipe · Advisor · Resume builder`  
**Brand:** JobPicks wordmark (Job + amber Picks), warm stone background, deck card mockup on right.

Do not put small text in the graphic — most users see it at thumbnail size.

---

## Promo text (170 chars, optional, updatable without release)

```
New: Swipe ranked job picks, chat with an AI career advisor, and tailor resumes — free to start. No auto-apply spam.
```

---

## What's New (release notes template)

```
Welcome to JobPicks on Android!

• Swipe a daily deck of AI-ranked job matches
• Save roles to your apply to-do list
• AI career advisor and resume builder
• Free plan with optional Pro upgrade

We never auto-apply — you stay in control of every application.
```

---

## Play Console checklist

- [ ] App name, short + full description pasted from this doc
- [ ] Marketing URL: `/welcome` returns 200 without login
- [ ] Privacy policy URL live
- [ ] Data safety form completed (account, resume, usage, billing via Stripe)
- [ ] Screenshots from real device (6 recommended)
- [ ] Feature graphic uploaded
- [ ] Content rating questionnaire completed
- [ ] Target countries: United States (expand later)
- [ ] Package name `com.jbuschmann.jobpicks` matches `assetlinks.json`

---

## Related docs

- [screenshot-guide.md](screenshot-guide.md) — capture instructions and overlay specs
- [../mobile-launch-checklist.md](../mobile-launch-checklist.md) — pre-submission gate
- [../domain-trademark-checklist.md](../domain-trademark-checklist.md) — JobPicks clearance
