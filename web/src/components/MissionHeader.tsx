import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useBilling } from "../hooks/useBilling";
import { useEngagement } from "../hooks/useEngagement";
import { openExternalUrl } from "../lib/openExternalUrl";
import { webUpgradeUrl } from "../lib/storefront";
import {
  anyPoolNearLimit,
  creditPoolsFromUsage,
  CreditWallet,
} from "./CreditWallet";
import { Button } from "./ui/Button";

type MissionHeaderProps = {
  variant?: "full" | "compact";
  className?: string;
};

export function MissionHeader({ variant = "full", className = "" }: MissionHeaderProps) {
  const { billing, loading: billingLoading } = useBilling();
  const { engagement, loading: engagementLoading } = useEngagement();
  const [checkoutBusy, setCheckoutBusy] = useState(false);

  if (billingLoading || engagementLoading) return null;

  const isPro = billing?.tier === "pro";
  const usage = billing?.usage;
  const pools = creditPoolsFromUsage(usage);
  const showUpgrade = !isPro && anyPoolNearLimit(pools, 80);
  const price = billing?.pro_monthly_price_cents
    ? `$${(billing.pro_monthly_price_cents / 100).toFixed(0)}/mo`
    : "$15/mo";

  async function startCheckout() {
    setCheckoutBusy(true);
    try {
      const res = await api.billing.checkout();
      await openExternalUrl(res.checkout_url);
    } catch (err) {
      console.error(err instanceof ApiError ? err.message : "Checkout failed");
    } finally {
      setCheckoutBusy(false);
    }
  }

  if (variant === "compact") {
    return (
      <div className={`flex flex-wrap items-center gap-2 ${className}`}>
        {engagement && engagement.streak_days > 0 ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-accent/25 bg-accent-muted/50 px-2.5 py-1 text-xs font-semibold text-accent-strong">
            <span aria-hidden>🔥</span>
            {engagement.streak_days}-day streak
          </span>
        ) : null}
        <CreditWallet pools={pools} compact />
      </div>
    );
  }

  return (
    <section
      className={`mb-4 overflow-hidden rounded-2xl border border-border-subtle bg-gradient-to-br from-surface via-surface-raised to-brand-muted/40 shadow-sm ${className}`}
    >
      <div className="border-b border-border-subtle/80 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            {engagement && engagement.streak_days > 0 ? (
              <div className="flex items-center gap-2">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-muted text-lg">
                  🔥
                </span>
                <div>
                  <p className="text-sm font-semibold text-ink-text">
                    {engagement.streak_days}-day streak
                  </p>
                  <p className="text-xs text-muted">Keep the momentum going</p>
                </div>
              </div>
            ) : (
              <div>
                <p className="text-sm font-semibold text-ink-text">Your job hunt</p>
                <p className="text-xs text-muted">Every action moves you forward</p>
              </div>
            )}
          </div>
          {engagement ? (
            <div className="text-right text-xs text-muted">
              <p>
                <span className="font-semibold text-ink-text">{engagement.applied_this_week}</span>{" "}
                applied this week
              </p>
              <p>
                <span className="font-semibold text-ink-text">{engagement.in_prep_count}</span> in
                your queue
              </p>
            </div>
          ) : null}
        </div>
      </div>

      {engagement?.focus_job ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle/60 bg-canvas/60 px-4 py-3">
          <div className="min-w-0">
            <p className="text-xs font-medium text-subtle">Today&apos;s focus</p>
            <p className="truncate text-sm font-semibold text-ink-text">
              {engagement.focus_job.title}
              <span className="font-normal text-muted"> · {engagement.focus_job.company}</span>
            </p>
          </div>
          <Link to={`/todo/${engagement.focus_job.id}/prepare`}>
            <Button size="sm">Prepare →</Button>
          </Link>
        </div>
      ) : null}

      {engagement?.pro_trial_active ? (
        <div className="border-b border-brand-strong/15 bg-brand-muted/50 px-4 py-2.5 text-xs text-brand-strong">
          <span className="font-semibold">Pro trial active</span>
          {engagement.pro_trial_ends_at ? (
            <span className="text-muted">
              {" "}
              — full access until{" "}
              {new Date(engagement.pro_trial_ends_at).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="px-4 py-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-xs font-medium text-subtle">
            {isPro ? "Pro plan · monthly credits" : "Free plan · credits remaining"}
          </p>
          <div className="flex items-center gap-3">
            <Link
              to="/progress"
              className="text-xs font-semibold text-brand-strong hover:text-brand-deep"
            >
              Progress
            </Link>
            {!isPro ? (
              <Link
                to="/settings"
                className="text-xs font-semibold text-brand-strong hover:text-brand-deep"
              >
                Plans
              </Link>
            ) : null}
          </div>
        </div>
        <CreditWallet pools={pools} />
        {showUpgrade && billing?.external_checkout_allowed && billing.stripe_configured ? (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-accent/25 bg-accent-muted/30 px-3 py-2.5">
            <p className="text-xs text-muted">
              You&apos;re getting value — Pro unlocks unlimited deck matches and 20 AI prep packets
              per month ({price}).
            </p>
            <Button size="sm" disabled={checkoutBusy} onClick={() => void startCheckout()}>
              {checkoutBusy ? "Redirecting…" : "Upgrade"}
            </Button>
          </div>
        ) : null}
        {showUpgrade && !billing?.external_checkout_allowed ? (
          <p className="mt-2 text-xs text-muted">
            Subscribe at{" "}
            <a href={webUpgradeUrl()} className="font-semibold text-brand-strong">
              {webUpgradeUrl()}
            </a>
          </p>
        ) : null}
      </div>
    </section>
  );
}
