import type { UsageQuota } from "../types";

export type CreditPool = {
  key: string;
  label: string;
  quota: UsageQuota;
};

function remaining(quota: UsageQuota): number | null {
  if (quota.unlimited || quota.limit == null) return null;
  return quota.remaining ?? Math.max(0, quota.limit - quota.used);
}

function usagePercent(quota: UsageQuota): number {
  if (quota.unlimited || quota.limit == null || quota.limit === 0) return 0;
  return Math.min(100, Math.round((quota.used / quota.limit) * 100));
}

function formatPoolLabel(pool: CreditPool): string {
  const left = remaining(pool.quota);
  if (left == null) return "Unlimited";
  if (pool.quota.lifetime) return `${left} left`;
  if (pool.quota.monthly) return `${left} this month`;
  return `${left} today`;
}

type CreditWalletProps = {
  pools: CreditPool[];
  compact?: boolean;
  className?: string;
};

export function CreditWallet({ pools, compact = false, className = "" }: CreditWalletProps) {
  const visible = pools.filter((p) => !p.quota.unlimited && p.quota.limit != null);
  if (visible.length === 0) return null;

  if (compact) {
    const lowest = visible.reduce(
      (acc, pool) => {
        const pct = usagePercent(pool.quota);
        if (!acc || pct > acc.pct) return { pool, pct };
        return acc;
      },
      null as { pool: CreditPool; pct: number } | null,
    );

    if (!lowest) return null;
    const warn = lowest.pct >= 80;
    return (
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${
          warn
            ? "border-accent/35 bg-accent-muted/60 text-accent-strong"
            : "border-border bg-surface text-muted"
        } ${className}`}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
        {lowest.pool.label}: {formatPoolLabel(lowest.pool)}
      </span>
    );
  }

  return (
    <div className={`grid gap-2 sm:grid-cols-2 ${className}`}>
      {visible.map((pool) => {
        const pct = usagePercent(pool.quota);
        const left = remaining(pool.quota);
        const warn = pct >= 80;
        const exhausted = left === 0;
        return (
          <div key={pool.key} className="min-w-0">
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span className="font-medium text-muted">{pool.label}</span>
              <span
                className={
                  exhausted
                    ? "font-semibold text-danger"
                    : warn
                      ? "font-semibold text-accent-strong"
                      : "text-ink-text"
                }
              >
                {formatPoolLabel(pool)}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-border-subtle">
              <div
                className={`h-full rounded-full transition-all ${
                  exhausted ? "bg-danger" : warn ? "bg-accent" : "bg-brand-strong"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function creditPoolsFromUsage(
  usage: import("../types").UsageSummary | null | undefined,
): CreditPool[] {
  if (!usage) return [];
  return [
    { key: "deck", label: "Deck swipes", quota: usage.deck_matches },
    { key: "packets", label: "AI prep packets", quota: usage.packets },
    { key: "advisor", label: "Advisor messages", quota: usage.advisor_messages },
    { key: "resume", label: "Resume sessions", quota: usage.resume_builder_messages },
  ];
}

export function anyPoolNearLimit(pools: CreditPool[], threshold = 80): boolean {
  return pools.some((pool) => {
    if (pool.quota.unlimited || pool.quota.limit == null) return false;
    return usagePercent(pool.quota) >= threshold;
  });
}
