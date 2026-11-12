import type { ReactNode } from "react";

export type PreparePhase = "decide" | "prepare" | "submit";

const PHASES: { key: PreparePhase; label: string; number: number }[] = [
  { key: "decide", label: "Decide", number: 1 },
  { key: "prepare", label: "Prepare", number: 2 },
  { key: "submit", label: "Submit", number: 3 },
];

type PreparePhaseNavProps = {
  current: PreparePhase;
  className?: string;
};

export function PreparePhaseNav({ current, className = "" }: PreparePhaseNavProps) {
  const currentIndex = PHASES.findIndex((p) => p.key === current);

  return (
    <div
      className={`sticky top-0 z-10 -mx-1 mb-4 border-b border-border-subtle bg-canvas/95 px-1 py-3 backdrop-blur-md ${className}`}
    >
      <div className="flex items-center justify-between gap-3">
        {PHASES.map((phase, index) => {
          const done = index < currentIndex;
          const active = index === currentIndex;
          return (
            <div key={phase.key} className="flex flex-1 items-center gap-2">
              <div className="flex min-w-0 flex-1 flex-col items-center gap-1">
                <span
                  className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
                    done
                      ? "bg-success-muted text-success"
                      : active
                        ? "bg-brand-strong text-on-brand"
                        : "bg-surface-raised text-subtle"
                  }`}
                >
                  {done ? "✓" : phase.number}
                </span>
                <span
                  className={`text-[11px] font-semibold ${
                    active ? "text-ink-text" : done ? "text-muted" : "text-subtle"
                  }`}
                >
                  {phase.label}
                </span>
              </div>
              {index < PHASES.length - 1 ? (
                <span
                  className={`mb-4 h-px flex-1 ${done ? "bg-success/40" : "bg-border"}`}
                  aria-hidden
                />
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

type PreparePhaseSectionProps = {
  phase: PreparePhase;
  current: PreparePhase;
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
};

export function PreparePhaseSection({
  phase,
  current,
  title,
  children,
}: PreparePhaseSectionProps) {
  const phaseIndex = PHASES.findIndex((p) => p.key === phase);
  const currentIndex = PHASES.findIndex((p) => p.key === current);
  const isPast = phaseIndex < currentIndex;
  const isCurrent = phaseIndex === currentIndex;

  if (isPast) {
    return (
      <details className="rounded-[var(--radius-card)] border border-border bg-surface-raised/50">
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-muted">
          <span className="mr-2 text-success">✓</span>
          {title}
        </summary>
        <div className="border-t border-border-subtle px-4 py-3 opacity-80">{children}</div>
      </details>
    );
  }

  if (!isCurrent) {
    return (
      <div className="rounded-[var(--radius-card)] border border-dashed border-border bg-surface-raised/30 px-4 py-3">
        <p className="text-sm font-medium text-subtle">{title}</p>
        <p className="mt-1 text-xs text-muted">Complete the previous step to unlock</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="font-display text-lg text-ink-text">{title}</h3>
      {children}
    </div>
  );
}

export function inferPreparePhase(
  hasFit: boolean,
  answersReviewed: boolean,
  readyToSubmit: boolean,
): PreparePhase {
  if (readyToSubmit) return "submit";
  if (hasFit && answersReviewed) return "prepare";
  return "decide";
}
