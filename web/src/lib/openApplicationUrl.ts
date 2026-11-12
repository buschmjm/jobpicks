/** Open an employer application URL in the user's browser. */
export function openApplicationUrl(url: string): void {
  const trimmed = url.trim();
  if (!trimmed) return;
  window.open(trimmed, "_blank", "noopener,noreferrer");
}
