/** App Store storefront detection for WS-8.6 billing gates. */

import { appPublicBaseUrl } from "./mountPath";

export type AppClientKind = "web" | "mobile";

export function getAppClientKind(): AppClientKind {
  if (import.meta.env.VITE_MOBILE_BUILD === "true") {
    return "mobile";
  }
  const capacitor = (window as Window & { Capacitor?: { isNativePlatform?: () => boolean } })
    .Capacitor;
  if (capacitor?.isNativePlatform?.()) {
    return "mobile";
  }
  return "web";
}

export function getAppStorefront(): string | null {
  const fromEnv = import.meta.env.VITE_APP_STOREFRONT;
  if (typeof fromEnv === "string" && fromEnv.trim()) {
    return fromEnv.trim().toUpperCase();
  }
  return null;
}

export function appStorefrontHeaders(): Record<string, string> {
  if (getAppClientKind() !== "mobile") {
    return {};
  }
  const headers: Record<string, string> = { "X-App-Client": "mobile" };
  const storefront = getAppStorefront();
  if (storefront) {
    headers["X-App-Storefront"] = storefront;
  }
  return headers;
}

export function webUpgradeUrl(): string {
  return `${appPublicBaseUrl()}/settings`;
}
