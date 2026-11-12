# Capacitor mobile shell (JobPicks)

JobPicks ships as a **Capacitor** wrapper around the Vite/React web app in `web/`.

## Prerequisites

- Node 20+
- JDK 17+ and Android Studio (Android SDK)
- Apple Developer account (iOS, deferred)
- Domain + `.well-known` files live (see [docs/mobile-launch-checklist.md](../docs/mobile-launch-checklist.md))

## First-time Android setup

```bash
# From repo root
npm install
cd web && npm install && cd ..
chmod +x scripts/*.sh

# Generate launcher icons + build mobile web bundle + create android/
npm run android:scaffold
```

`capacitor.config.ts` uses:

- **appId:** `com.jbuschmann.jobpicks`
- **appName:** `JobPicks`
- **webDir:** `web/dist`

## Mobile web build env

Baked in by `scripts/build-mobile-web.sh`:

```env
VITE_MOBILE_BUILD=true
VITE_APP_STOREFRONT=US
VITE_APP_BASE_URL=https://app.willowriverautomation.com
```

## After web changes

```bash
npm run android:sync
npm run android:open   # Android Studio
```

Release AAB (requires signing keystore in `android/`):

```bash
cd android && ./gradlew bundleRelease
```

## Auth

- OAuth redirect: `https://app.willowriverautomation.com/auth/callback`
- Legacy host `jobs.jbuschmann.com` still works via `APP_ALT_BASE_URLS`
- Set `ANDROID_SHA256_CERT_FINGERPRINT` in cluster ConfigMap after creating upload keystore
- Verify: `bash deploy/scripts/verify-well-known.sh`

## Billing (US storefront)

Stripe Checkout opens in the system browser via `@capacitor/browser` (`web/src/lib/openExternalUrl.ts`).

## Play Store status

See [docs/play-store-readiness.md](../docs/play-store-readiness.md) for what's done vs. owner-only tasks.
