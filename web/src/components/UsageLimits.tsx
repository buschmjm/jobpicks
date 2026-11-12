import { Link } from "react-router-dom";
import { Button } from "./ui/Button";
import { Alert } from "./ui/Alert";
import { webUpgradeUrl } from "../lib/storefront";

export type UsageQuota = {
  used: number;
  limit: number | null;
  remaining: number | null;
  unlimited: boolean;
  resets_at?: string | null;
  lifetime?: boolean;
  monthly?: boolean;
};

type UsageMeterProps = {
  label: string;
  quota: UsageQuota;
  className?: string;
};

function formatRemaining(quota: UsageQuota): string {
  if (quota.unlimited || quota.limit == null) {
    return "Unlimited";
  }
  const remaining = quota.remaining ?? Math.max(0, quota.limit - quota.used);
  if (quota.lifetime) {
    return `${remaining} of ${quota.limit} left (lifetime)`;
  }
  if (quota.monthly) {
    return `${remaining} of ${quota.limit} left this month`;
  }
  return `${remaining} of ${quota.limit} left today`;
}

export function UsageMeter({ label, quota, className = "" }: UsageMeterProps) {
  const remaining = quota.remaining ?? (quota.limit != null ? Math.max(0, quota.limit - quota.used) : null);
  const low = quota.limit != null && !quota.unlimited && remaining != null && remaining <= 1;
  const exhausted = quota.limit != null && !quota.unlimited && remaining === 0;

  return (
    <div className={`flex items-center justify-between gap-3 text-sm ${className}`}>
      <span className="text-muted">{label}</span>
      <span
        className={
          exhausted ? "font-semibold text-danger" : low ? "font-semibold text-accent" : "text-ink-text"
        }
      >
        {formatRemaining(quota)}
      </span>
    </div>
  );
}

type UsageBannerProps = {
  quota: UsageQuota;
  featureLabel: string;
  stripeConfigured?: boolean;
  externalCheckoutAllowed?: boolean;
  onUpgrade?: () => void;
  upgradeBusy?: boolean;
  className?: string;
};

export function UsageBanner({
  quota,
  featureLabel,
  stripeConfigured = false,
  externalCheckoutAllowed = true,
  onUpgrade,
  upgradeBusy = false,
  className = "",
}: UsageBannerProps) {
  if (quota.unlimited || quota.limit == null) {
    return null;
  }
  const remaining = quota.remaining ?? Math.max(0, quota.limit - quota.used);
  const usedPct =
    quota.limit != null && quota.limit > 0 ? Math.round((quota.used / quota.limit) * 100) : 0;
  if (remaining > 1 && usedPct < 80) {
    return null;
  }

  const tone = remaining === 0 ? "warning" : "info";
  return (
    <Alert tone={tone} className={className}>
      {remaining === 0 ? (
        <p className="text-sm">
          You&apos;ve used all {quota.limit} free {featureLabel}
          {quota.lifetime ? " (lifetime)" : quota.monthly ? " this month" : " for today"}. Upgrade to
          Pro for higher limits.
        </p>
      ) : (
        <p className="text-sm">
          <span className="font-semibold text-ink-text">
            {remaining === 1 ? "1" : `${Math.round(usedPct)}%`} {featureLabel.slice(0, -1)}
            {remaining === 1 ? " left" : " used"}
          </span>
          {quota.lifetime ? " on your free plan." : quota.monthly ? " this month." : " today."}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {stripeConfigured && externalCheckoutAllowed && onUpgrade ? (
          <Button size="sm" disabled={upgradeBusy} onClick={onUpgrade}>
            {upgradeBusy ? "Redirecting…" : "Upgrade to Pro"}
          </Button>
        ) : null}
        {!externalCheckoutAllowed ? (
          <p className="text-sm text-muted">
            Subscribe at{" "}
            <a href={webUpgradeUrl()} className="font-semibold text-brand-strong hover:text-brand-deep">
              {webUpgradeUrl()}
            </a>
          </p>
        ) : null}
        <Link
          to="/settings"
          className="inline-flex items-center justify-center rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-ink-text shadow-sm hover:border-muted hover:bg-surface-raised"
        >
          View plans
        </Link>
      </div>
    </Alert>
  );
}
