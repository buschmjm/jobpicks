import { Link } from "react-router-dom";
import { UsageMeter } from "./UsageLimits";
import { Button } from "./ui/Button";
import type { BillingStatus } from "../types";
import { webUpgradeUrl } from "../lib/storefront";

const PRO_HIGHLIGHTS = [
  "All available deck matches each day (vs 10 on Free)",
  "80 career advisor messages per month",
  "20 resume builder sessions per month",
  "Full “why it fits” explanations + score breakdown",
  "Intraday alerts for strong new matches",
  "20 AI application packets per month",
] as const;

type PlanDetailsPanelProps = {
  billing: BillingStatus;
  billingBusy?: boolean;
  onUpgrade?: () => void;
  onManageBilling?: () => void;
  onCancel?: () => void;
  compact?: boolean;
};

function formatDeckCap(cap: number | null | undefined): string {
  if (cap == null) {
    return "All available deck matches per day";
  }
  return `Up to ${cap} deck matches per day`;
}

export function PlanDetailsPanel({
  billing,
  billingBusy = false,
  onUpgrade,
  onManageBilling,
  onCancel,
  compact = false,
}: PlanDetailsPanelProps) {
  const isPro = billing.tier === "pro";
  const proPriceCents = billing.pro_monthly_price_cents ?? billing.price_variant_cents ?? 1500;

  return (
    <div className={`space-y-4 rounded-[var(--radius-card)] border border-border bg-surface-raised p-4 ${compact ? "" : "mt-4"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-ink-text">
          Current plan:{" "}
          <span className={isPro ? "text-brand-strong" : "text-muted"}>
            {isPro ? "Pro" : "Free"}
          </span>
        </p>
        {isPro && billing.subscription_period_end ? (
          <p className="text-xs text-subtle">
            {billing.subscription_status === "active"
              ? `Renews ${new Date(billing.subscription_period_end).toLocaleDateString()}`
              : `Access until ${new Date(billing.subscription_period_end).toLocaleDateString()}`}
          </p>
        ) : null}
      </div>

      <ul className="text-sm text-muted">
        <li>{formatDeckCap(billing.daily_topup_cap)}</li>
        <li>
          {billing.max_why_bullets === 1
            ? "1 “why it fits” bullet per card"
            : "Full “why it fits” explanations"}
        </li>
        {billing.show_score_breakdown ? <li>Match score breakdown on cards</li> : null}
        {billing.intraday_alerts ? <li>Intraday alerts for strong new matches</li> : null}
        {isPro ? (
          <li>Monthly AI limits for advisor, resume builder, and application packets</li>
        ) : billing.lifetime_packets_limit != null ? (
          <li>
            {billing.lifetime_packets_used}/{billing.lifetime_packets_limit} AI application packets
            used (lifetime)
          </li>
        ) : null}
      </ul>

      {billing.usage ? (
        <div className="space-y-2 border-t border-border-subtle pt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-subtle">
            {isPro ? "This month's usage" : "Today's usage & limits"}
          </p>
          <UsageMeter label="Deck matches added" quota={billing.usage.deck_matches} />
          <UsageMeter label="Career advisor messages" quota={billing.usage.advisor_messages} />
          <UsageMeter label="Resume builder messages" quota={billing.usage.resume_builder_messages} />
          <UsageMeter label="AI application packets" quota={billing.usage.packets} />
        </div>
      ) : null}

      {!isPro ? (
        <div className="rounded-xl border border-accent/20 bg-brand-muted/40 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-strong">Pro includes</p>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            {PRO_HIGHLIGHTS.map((item) => (
              <li key={item}>• {item}</li>
            ))}
          </ul>
          <p className="mt-3 text-sm text-muted">
            ${(proPriceCents / 100).toFixed(2)}/month — cancel anytime.
          </p>
        </div>
      ) : (
        <p className="text-sm text-muted">
          Pro includes generous monthly AI limits designed to cover active job searches without
          unlimited API risk.
        </p>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        {!isPro && billing.stripe_configured && billing.external_checkout_allowed && onUpgrade ? (
          <Button size="sm" disabled={billingBusy} onClick={onUpgrade}>
            {billingBusy ? "Redirecting…" : "Upgrade to Pro"}
          </Button>
        ) : null}
        {!isPro && billing.stripe_configured && !billing.external_checkout_allowed ? (
          <p className="text-xs text-subtle">
            Subscribe on the web at{" "}
            <a href={webUpgradeUrl()} className="font-semibold text-brand-strong hover:text-brand-deep">
              {webUpgradeUrl()}
            </a>
          </p>
        ) : null}
        {isPro && billing.stripe_configured && onManageBilling ? (
          <>
            <Button size="sm" variant="secondary" disabled={billingBusy} onClick={onManageBilling}>
              Manage billing
            </Button>
            {onCancel ? (
              <Button size="sm" variant="ghost" disabled={billingBusy} onClick={onCancel}>
                Cancel Pro
              </Button>
            ) : null}
          </>
        ) : null}
        {!compact ? (
          <Link
            to="/settings"
            className="inline-flex items-center justify-center rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-ink-text shadow-sm hover:border-muted hover:bg-surface-raised"
          >
            Plan settings
          </Link>
        ) : null}
      </div>
    </div>
  );
}
