#!/usr/bin/env bash
# First-time Android native project setup. Requires JDK 17+ and Android SDK (Android Studio).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

if ! command -v java >/dev/null 2>&1; then
  echo "ERROR: Java JDK 17+ required. Install Android Studio or: sudo apt install openjdk-17-jdk" >&2
  exit 1
fi

if [[ -z "${ANDROID_HOME:-}" && ! -d "${HOME}/Android/Sdk" ]]; then
  echo "ERROR: ANDROID_HOME not set. Install Android Studio and SDK." >&2
  exit 1
fi

export ANDROID_HOME="${ANDROID_HOME:-${HOME}/Android/Sdk}"

npm install
npm run icons:generate
npm run mobile:build:web

if [[ ! -d android ]]; then
  npx cap add android
fi

npx cap sync android
echo "Android project ready. Open with: npm run android:open"
echo "Release AAB: cd android && ./gradlew bundleRelease"
