import type { ApplicationStep } from "../types";

type ApplicationProgressStepperProps = {
  stepsDone: number;
  stepsTotal: number;
  steps?: ApplicationStep[];
  compact?: boolean;
};

const PHASES = ["Prep", "Apply", "Done"] as const;

function phaseFromProgress(done: number, total: number): number {
  if (total === 0) return 0;
  const ratio = done / total;
  if (ratio >= 1) return 2;
  if (ratio >= 0.5) return 1;
  return 0;
}

export function ApplicationProgressStepper({
  stepsDone,
  stepsTotal,
  compact = false,
}: ApplicationProgressStepperProps) {
  const activePhase = phaseFromProgress(stepsDone, stepsTotal);

  if (compact) {
    return (
      <div className="flex items-center gap-1.5">
        {PHASES.map((label, index) => (
          <div key={label} className="flex items-center gap-1.5">
            <span
              className={`h-2 w-2 rounded-full ${
                index < activePhase
                  ? "bg-success"
                  : index === activePhase
                    ? "bg-accent"
                    : "bg-border"
              }`}
            />
            {index < PHASES.length - 1 ? (
              <span className="h-px w-3 bg-border" aria-hidden />
            ) : null}
          </div>
        ))}
        {stepsTotal > 0 ? (
          <span className="ml-1 text-[11px] text-muted">
            {stepsDone}/{stepsTotal}
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {PHASES.map((label, index) => {
        const done = index < activePhase;
        const active = index === activePhase;
        return (
          <div key={label} className="flex items-center gap-2">
            <div className="flex items-center gap-1.5">
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold ${
                  done
                    ? "bg-success-muted text-success"
                    : active
                      ? "bg-accent-muted text-accent-strong"
                      : "bg-surface-raised text-subtle"
                }`}
              >
                {done ? "✓" : index + 1}
              </span>
              <span
                className={`text-xs font-medium ${
                  active ? "text-ink-text" : done ? "text-muted" : "text-subtle"
                }`}
              >
                {label}
              </span>
            </div>
            {index < PHASES.length - 1 ? (
              <span
                className={`h-px w-6 ${index < activePhase ? "bg-success/40" : "bg-border"}`}
                aria-hidden
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
