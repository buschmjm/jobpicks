import { Link } from "react-router-dom";
import { useEngagement } from "../hooks/useEngagement";
import { useBilling } from "../hooks/useBilling";
import { PageHeader } from "../components/ui/PageHeader";
import { SurfaceCard } from "../components/ui/Alert";
import { creditPoolsFromUsage, CreditWallet } from "../components/CreditWallet";
import { MILESTONE_LABELS } from "../types";

export function ProgressPage() {
  const { engagement, loading } = useEngagement();
  const { billing } = useBilling();
  const pools = creditPoolsFromUsage(billing?.usage);

  if (loading || !engagement) {
    return <p className="py-10 text-center text-muted">Loading your progress…</p>;
  }

  return (
    <div className="pb-6">
      <PageHeader
        title="Your progress"
        subtitle="Track momentum across your job hunt — every application counts."
      />

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <SurfaceCard className="text-center">
          <p className="text-3xl font-display text-ink-text">{engagement.applied_this_week}</p>
          <p className="mt-1 text-sm text-muted">Applied this week</p>
        </SurfaceCard>
        <SurfaceCard className="text-center">
          <p className="text-3xl font-display text-ink-text">{engagement.applied_total}</p>
          <p className="mt-1 text-sm text-muted">Total applications</p>
        </SurfaceCard>
        <SurfaceCard className="text-center">
          <p className="text-3xl font-display text-ink-text">
            {engagement.streak_days > 0 ? (
              <>
                <span aria-hidden>🔥 </span>
                {engagement.streak_days}
              </>
            ) : (
              "—"
            )}
          </p>
          <p className="mt-1 text-sm text-muted">Day streak</p>
        </SurfaceCard>
      </div>

      <SurfaceCard className="mt-4">
        <p className="text-sm font-semibold text-ink-text">Credits remaining</p>
        <div className="mt-3">
          <CreditWallet pools={pools} />
        </div>
        {billing?.tier === "free" ? (
          <Link
            to="/settings"
            className="mt-3 inline-block text-sm font-semibold text-brand-strong hover:text-brand-deep"
          >
            View Pro plans →
          </Link>
        ) : null}
      </SurfaceCard>

      <SurfaceCard className="mt-4">
        <p className="text-sm font-semibold text-ink-text">Milestones</p>
        {engagement.milestones.length === 0 ? (
          <p className="mt-2 text-sm text-muted">
            Prep your first application or mark a job applied to start earning milestones.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {engagement.milestones.map((m) => (
              <li
                key={m.id}
                className="flex items-center gap-2 rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm"
              >
                <span className="text-success">✓</span>
                <span className="font-medium text-ink-text">
                  {MILESTONE_LABELS[m.id] ?? m.label}
                </span>
              </li>
            ))}
          </ul>
        )}
      </SurfaceCard>

      {engagement.longest_streak > 0 ? (
        <p className="mt-4 text-center text-xs text-muted">
          Longest streak: {engagement.longest_streak} day{engagement.longest_streak === 1 ? "" : "s"}
        </p>
      ) : null}
    </div>
  );
}
