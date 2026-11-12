# Screenshot & creative guide — JobPicks Play Store

Assets for the Play Store listing and the `/welcome` marketing page. Replace CSS mockups
on the welcome page with real screenshots once the Android build is available.

---

## Brand reference

| Token | Value |
|-------|--------|
| Wordmark | Job**Picks** (Picks in amber `#b45309`) |
| Background | Warm stone `#fafaf9` / white |
| Accent | Amber `#b45309` |
| Fonts | Plus Jakarta Sans (UI), Instrument Serif (headlines) |
| Logo | Stacked deck cards SVG (see `web/src/components/BrandLogo.tsx`) |

---

## Phone screenshots (required)

### Technical specs

| Spec | Value |
|------|--------|
| Format | PNG or JPEG |
| Min size | 320px short side |
| Recommended | 1080×1920 (9:16) |
| Max per screenshot | 8 MB |
| Count | Minimum 2; recommend 6–8 |

### Capture workflow

1. Build Android internal testing APK with `VITE_MOBILE_BUILD=true`.
2. Seed a demo account with:
   - Completed onboarding (resume uploaded)
   - At least 5 deck cards with varied match scores (85–95%)
   - One saved to-do item
   - Advisor thread with a realistic Q&A
   - Resume builder with visible preview pane
3. Use **light mode**, status bar clean, no debug banners.
4. Capture on a mid-size phone (Pixel class) for representative framing.

### Screen order (story arc)

1. **Hook** — Deck card with high match score visible
2. **Trust** — "Why it fits" or score breakdown (Pro user or free single bullet)
3. **Action** — Apply to-do list with 2–3 items
4. **Depth** — Career advisor conversation
5. **Depth** — Resume builder split view
6. **Monetization** — Settings showing Free limits + Pro CTA (not pushy)

### Optional text overlays

Keep overlays large and minimal (max 5 words). Suggested:

| Screenshot | Overlay text |
|------------|--------------|
| Deck | Jobs picked for you |
| Match detail | See why it fits |
| To-do | Your apply queue |
| Advisor | AI career advisor |
| Resume | Tailor your resume |
| Settings | Free to start |

Use brand fonts and amber accent on overlays. Export at 2× for sharpness.

---

## Feature graphic (1024×500)

Single image shown at top of store listing.

**Layout:**
- Left 55%: headline + subline on `#fafaf9` gradient
- Right 45%: phone mockup showing deck screen (real screenshot composited)

**Copy:**
- Headline: `Jobs picked for your profile`
- Subline: `Swipe · Advisor · Resume builder`

**Do not include:** pricing, fine print, QR codes, or Play badge (Google adds its own).

---

## App icon

- 512×512 PNG for Play Console
- Adapt deck-card mark from `BrandMark` component
- Amber accent line on top card; stone/white stack
- No text in icon (illegible at small sizes)

---

## Promo video (optional, 30s)

| Time | Visual | VO / text |
|------|--------|-----------|
| 0–5s | Deck swipe | "Tired of scrolling endless job boards?" |
| 5–12s | Match score + save | "JobPicks ranks roles for your profile." |
| 12–20s | Advisor + resume | "Get advice and tailor your resume." |
| 20–27s | To-do apply | "You apply when you're ready. No spam." |
| 27–30s | Logo + CTA | "JobPicks — free to start." |

---

## Updating the welcome page

After screenshots exist:

1. Export optimized WebP/PNG to `web/public/marketing/` or `api/static/pages/assets/`.
2. Replace CSS phone mockups in `api/static/pages/welcome.html` with `<img>` tags.
3. Add `loading="lazy"` and width/height to avoid layout shift.

Until then, the CSS mockups on `/welcome` are intentional placeholders for store reviewers
and early visitors.
