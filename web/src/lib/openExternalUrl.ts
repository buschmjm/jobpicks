import { getAppClientKind } from "./storefront";

/** Open Stripe checkout / portal in system browser on native; same tab on web. */
export async function openExternalUrl(url: string): Promise<void> {
  if (getAppClientKind() === "mobile") {
    const { Browser } = await import("@capacitor/browser");
    await Browser.open({ url });
    return;
  }
  window.location.href = url;
}
