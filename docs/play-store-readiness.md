# Play Store readiness — JobPicks

Last updated: 2026-09-04. Tracks what agents automated vs. what requires the owner.

## Automated in repo (done)

| Item | Location |
|------|----------|
| Product rebrand (user-facing UI) | `web/`, `api/routers/pages.py` |
| Package ID `com.jbuschmann.jobpicks` | `capacitor.config.ts`, `deploy/k8s/base/configmap.yaml` |
| Capacitor deps + root scripts | `package.json`, `web/package.json` |
| Mobile web build script | `scripts/build-mobile-web.sh` |
| Android scaffold script | `scripts/scaffold-android.sh` |
| Stripe → system browser on native | `web/src/lib/openExternalUrl.ts` |
| Mobile env types | `web/src/vite-env.d.ts` |
| Auth alt redirect URIs | `api/routers/auth.py`, Keycloak bootstrap |
| App icon 512×512 | `docs/store-listing/icon-512.png` (run `npm run icons:generate`) |
| Store listing copy | `docs/store-listing/play-store.md` |
| Marketing URL | `https://willowriverautomation.com/jobpicks` |
| App URL | `https://app.willowriverautomation.com` |
| Privacy / terms | `/privacy`, `/terms` |

## Owner actions required (cannot automate here)

### 1. DNS — `app.willowriverautomation.com`

Add CNAME at Netlify/registrar → `8fadd2f1-c663-4a9e-913a-83f28a4a6da9.cfargotunnel.com`  
Runbook: `homelab-infra/docs/runbooks/jobpicks-app-subdomain.md`

### 2. Android native project (needs Android Studio machine)

```bash
cd job-platform
npm run android:scaffold
```

Commit the generated `android/` directory after first successful scaffold.

### 3. Release signing keystore

```bash
keytool -genkey -v -keystore jobpicks-upload.keystore -alias jobpicks \
  -keyalg RSA -keysize 2048 -validity 10000
```

Configure `android/app/build.gradle` signingConfigs (Android Studio → Generate Signed Bundle).

Export SHA-256 fingerprint:

```bash
keytool -list -v -keystore jobpicks-upload.keystore -alias jobpicks | grep SHA256
```

Set in cluster ConfigMap:

```yaml
ANDROID_SHA256_CERT_FINGERPRINT: "AA:BB:..."
```

Redeploy + verify `curl https://app.willowriverautomation.com/.well-known/assetlinks.json`

### 4. Build signed AAB

```bash
npm run android:sync
cd android && ./gradlew bundleRelease
# Output: android/app/build/outputs/bundle/release/app-release.aab
```

### 5. Play Console (manual)

- [ ] Create app with package `com.jbuschmann.jobpicks`
- [ ] Upload AAB to internal testing
- [ ] Paste listing from `docs/store-listing/play-store.md`
- [ ] Upload 6 screenshots from real device
- [ ] Upload feature graphic 1024×500
- [ ] Upload `docs/store-listing/icon-512.png`
- [ ] Complete Data safety form
- [ ] Content rating questionnaire
- [ ] Support email on product domain

### 6. Real-device QA

- [ ] Sign in via Keycloak on Android
- [ ] Swipe deck, save to-do, advisor chat
- [ ] Upgrade → Stripe Checkout in system browser
- [ ] Pro unlocks after web subscription

### 7. Stripe live keys

Wire production Stripe secrets (see `deploy/secrets/` template).

## CI

`.github/workflows/android-debug.yml` builds a debug APK when `android/` exists (after scaffold).

## Verdict

**Not upload-ready until:** Android scaffold + keystore + AAB + Play Console listing + device QA.  
**Marketing and backend:** ready. **Native shell:** scripts ready; run on a machine with Android Studio.
