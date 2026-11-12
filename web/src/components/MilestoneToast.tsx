import { useEffect } from "react";
import { MILESTONE_LABELS } from "../types";

type MilestoneToastProps = {
  milestoneIds: string[];
  onDismiss: () => void;
};

export function MilestoneToast({ milestoneIds, onDismiss }: MilestoneToastProps) {
  useEffect(() => {
    if (milestoneIds.length === 0) return;
    const timer = window.setTimeout(onDismiss, 6000);
    return () => window.clearTimeout(timer);
  }, [milestoneIds, onDismiss]);

  if (milestoneIds.length === 0) return null;

  const label = milestoneIds
    .map((id) => MILESTONE_LABELS[id] ?? id)
    .join(" · ");

  return (
    <div className="pointer-events-none fixed bottom-20 left-1/2 z-50 w-[min(92vw,24rem)] -translate-x-1/2 animate-in fade-in slide-in-from-bottom-4 sm:bottom-6">
      <div className="pointer-events-auto rounded-2xl border border-accent/30 bg-canvas px-4 py-3 shadow-lg">
        <p className="text-xs font-semibold uppercase tracking-wide text-accent-strong">
          Milestone unlocked
        </p>
        <p className="mt-1 text-sm font-semibold text-ink-text">{label}</p>
        <button
          type="button"
          onClick={onDismiss}
          className="mt-2 text-xs font-medium text-muted hover:text-ink-text"
        >
          Nice!
        </button>
      </div>
    </div>
  );
}
