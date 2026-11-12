import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { openExternalUrl } from "../lib/openExternalUrl";
import { webUpgradeUrl } from "../lib/storefront";
import { Button } from "./ui/Button";

type CheckoutButtonProps = {
  label?: string;
  size?: "sm" | "md" | "lg";
  stripeConfigured?: boolean;
  externalCheckoutAllowed?: boolean;
  className?: string;
};

export function CheckoutButton({
  label = "Upgrade to Pro",
  size = "sm",
  stripeConfigured = false,
  externalCheckoutAllowed = true,
  className = "",
}: CheckoutButtonProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startCheckout() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.billing.checkout();
      await openExternalUrl(res.checkout_url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start checkout");
    } finally {
      setBusy(false);
    }
  }

  if (!externalCheckoutAllowed) {
    return (
      <p className={`text-sm text-muted ${className}`}>
        Subscribe at{" "}
        <a href={webUpgradeUrl()} className="font-semibold text-brand-strong hover:text-brand-deep">
          {webUpgradeUrl()}
        </a>
      </p>
    );
  }

  return (
    <div className={className}>
      {stripeConfigured ? (
        <Button size={size} disabled={busy} onClick={() => void startCheckout()}>
          {busy ? "Redirecting…" : label}
        </Button>
      ) : null}
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
    </div>
  );
}

export function ViewPlansLink({ className = "" }: { className?: string }) {
  return (
    <Link
      to="/settings"
      className={`inline-flex items-center justify-center rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-ink-text shadow-sm hover:border-muted hover:bg-surface-raised ${className}`}
    >
      View plans
    </Link>
  );
}
