# Domain and trademark clearance (WS-8 gate)

Complete **before** fixing the Capacitor `appId` or submitting to App Store / Play Store.
Universal Links and Android App Links bake the product domain into the shipped binary.

## Decision (2026-09-04)

| Item | Chosen value |
|------|----------------|
| **Product name** | **JobPicks** |
| **Fallbacks considered** | JobMatcher (rejected — `jobmatcher.app` live competitor), CustomJobs (clean but weaker ASO) |
| **Primary domain to register** | `jobpicks.com` (+ `jobpicks.app` recommended) |
| **Current app host** | `jobs.jbuschmann.com` (beta; keep until custom domain cutover) |
| **iOS bundle ID** | `com.jbuschmann.jobpicks` (rename from `jobdeck` before store submit) |
| **Android package** | `com.jbuschmann.jobpicks` |
| **Play Store app name** | `JobPicks: AI Job Match` |
| **Marketing URL** | `https://jobs.jbuschmann.com/welcome` |

## 1. Name clearance

| Step | Action | Status |
|------|--------|--------|
| USPTO TESS | Search "JobPicks" and close variants | ☐ |
| App Store | Search existing apps named JobPicks | ☐ (no exact match found 2026-09-04) |
| Play Store | Same search on Google Play | ☐ (no exact match found 2026-09-04) |
| Web | Google `"JobPicks" job search` for collision risk | ☐ (minor: PickJobs, JobPics — different brands) |

## 2. Domain

| Candidate | Check registrar | Point DNS to homelab / Cloudflare |
|-----------|-----------------|-----------------------------------|
| `jobpicks.com` | ☐ register | ☐ |
| `jobpicks.app` | ☐ register | ☐ |
| `jobs.jbuschmann.com` (current beta) | ✓ | ✓ |

Set `APP_BASE_URL` and `EMAIL_FROM` to the **same product domain** you ship in mobile builds.
After `jobpicks.com` cutover, update `APP_BASE_URL`, email DKIM, and `.well-known` files.

## 3. Record decision

- Chosen product name: **JobPicks**
- Chosen product domain (target): **jobpicks.com**
- Current production host: **jobs.jbuschmann.com**
- iOS bundle ID: `com.jbuschmann.jobpicks`
- Android package: `com.jbuschmann.jobpicks`
- Trademark status: preliminary clearance — proceed with registration; formal TESS search pending

## 4. Blockers

Do **not** start WS-8 Capacitor store submission until:

1. Domain resolves to production with valid TLS
2. `.well-known` files verify (`deploy/scripts/verify-well-known.sh`)
3. Cloudflare (if used) allows mobile user agents on public paths (see [mobile-launch-checklist.md](mobile-launch-checklist.md))
4. Full rebrand from JobDeck → JobPicks in app binary and store listing
