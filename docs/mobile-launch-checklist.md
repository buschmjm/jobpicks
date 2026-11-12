# Mobile launch checklist (WS-8)

Pre-submission gate for Capacitor iOS/Android builds. See also
[domain-trademark-checklist.md](domain-trademark-checklist.md) and
[email-deliverability.md](email-deliverability.md).

## Public paths (must be anonymous — no Keycloak `jobs` role)

These routes are allowlisted in `api/access_control.py` (A7). Verify each returns
**200** without auth, including from a **mobile user agent**:

```bash
export APP_BASE_URL=https://jobs.jbuschmann.com
bash deploy/scripts/verify-well-known.sh
```

| Path | Purpose |
|------|---------|
| `GET /.well-known/apple-app-site-association` | iOS Universal Links |
| `GET /.well-known/assetlinks.json` | Android App Links |
| `GET /api/mobile/readiness` | Deploy smoke (config flags) |
| `GET /api/auth/config` | OIDC client metadata |
| `POST /api/auth/oidc/token` | PKCE token exchange |
| `GET /privacy` | App Store privacy URL |
| `GET /welcome` | Legacy marketing URL (optional redirect to WRA) |
| `POST /api/billing/webhook` | Stripe (POST only; 4xx without signature is OK) |

## Cluster config (ConfigMap + secrets)

| Variable | Where | Notes |
|----------|-------|-------|
| `APPLE_TEAM_ID` | ConfigMap | 10-char Apple Developer team ID |
| `APPLE_BUNDLE_ID` | ConfigMap | `com.jbuschmann.jobpicks` |
| `ANDROID_PACKAGE` | ConfigMap | `com.jbuschmann.jobpicks` |
| `ANDROID_SHA256_CERT_FINGERPRINT` | ConfigMap | Play signing cert fingerprint |
| `EXTERNAL_CHECKOUT_STOREFRONTS` | ConfigMap | Default `US` — App Store regions allowed in-app Stripe CTA |
| `APP_BASE_URL` | ConfigMap | Must match shipped domain |

After deploy:

```bash
curl -sf "$APP_BASE_URL/api/mobile/readiness" | jq
```

Expect `apple_universal_links_configured: true` once `APPLE_TEAM_ID` is set.

## Cloudflare / edge rules

If Cloudflare bot fight or oauth2-proxy sits in front of the app:

1. **Do not** put oauth2-proxy in front of the whole site — it breaks `.well-known` and webhooks.
2. Allow mobile Safari / Chrome user agents on `/auth/callback` and `/.well-known/*`.
3. Verify from a phone (or script with iPhone UA) that `/auth/callback` is not challenged.

## WS-8.6 — Region-gated billing

- **US App Store:** upgrade CTA opens Stripe Checkout (via `@capacitor/browser` in native build).
- **Non-US storefronts:** app hides in-app upgrade CTA; users subscribe on the web. Pro still works in-app (3.1.3(b) Multiplatform Services).
- Mobile builds set `VITE_MOBILE_BUILD=true` and `VITE_APP_STOREFRONT=US` (or user's storefront).
- API reads `X-App-Client: mobile` and `X-App-Storefront` headers.

## Capacitor scaffold

See [mobile/README.md](../mobile/README.md) for `capacitor.config.ts` and native project setup.

## Real-device QA (WS-8.8) — not automatable in CI

1. Install TestFlight / internal APK build
2. Sign in via Universal Link → `/auth/callback` → app receives token
3. Swipe deck → add todo → open Prepare → generate packet
4. US storefront: tap Upgrade → Stripe Checkout opens in system browser
5. EU storefront build: Upgrade hidden; web subscription still unlocks Pro in app

## Store listing assets (before submission)

Copy and readiness tracker: [docs/play-store-readiness.md](play-store-readiness.md)
and [docs/store-listing/screenshot-guide.md](store-listing/screenshot-guide.md).

- Live marketing URL: `https://willowriverautomation.com/jobpicks` (no auth required)
- Homelab fallback: `https://jobs.jbuschmann.com/welcome` until WRA page is deployed
- Support email (`privacy@` or `support@` on product domain)
- Privacy policy URL (`/privacy`)
- Screenshots from real device (not desktop-only)
- Feature graphic 1024×500 (see screenshot guide)
- App name: `JobPicks: AI Job Match` (30 char limit)
