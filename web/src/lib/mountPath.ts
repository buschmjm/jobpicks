/** Base path when the SPA is served under a subpath (e.g. /jobpicks). */

function normalizeMountPath(path: string | undefined): string {
  const raw = (path ?? "").trim().replace(/\/$/, "");
  if (!raw || raw === "/") {
    return "";
  }
  return raw.startsWith("/") ? raw : `/${raw}`;
}

export const APP_MOUNT_PATH = normalizeMountPath(import.meta.env.VITE_APP_MOUNT_PATH);

export const API_BASE = APP_MOUNT_PATH ? `${APP_MOUNT_PATH}/api` : "/api";

export function withMountPath(path: string): string {
  if (!path.startsWith("/")) {
    return path;
  }
  if (!APP_MOUNT_PATH) {
    return path;
  }
  if (path === APP_MOUNT_PATH || path.startsWith(`${APP_MOUNT_PATH}/`)) {
    return path;
  }
  return `${APP_MOUNT_PATH}${path}`;
}

export function appPublicBaseUrl(): string {
  const { hostname, origin } = window.location;
  const knownHosts = new Set([
    "jobs.jbuschmann.com",
    "jobs-dev.jbuschmann.com",
    "app.willowriverautomation.com",
    "localhost",
    "127.0.0.1",
  ]);
  if (knownHosts.has(hostname)) {
    return origin + (APP_MOUNT_PATH || "");
  }
  const configured = import.meta.env.VITE_APP_BASE_URL;
  if (typeof configured === "string" && configured.trim()) {
    return configured.replace(/\/$/, "");
  }
  return origin + (APP_MOUNT_PATH || "");
}
