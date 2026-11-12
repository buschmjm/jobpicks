import type { LeftSwipeReason } from "../types";
import { LEFT_SWIPE_REASONS } from "../types";
import { Button } from "./ui/Button";

interface ReasonChipsProps {
  selected: LeftSwipeReason | null;
  onSelect: (reason: LeftSwipeReason) => void;
  onSkipReason: () => void;
  onCancel: () => void;
}

export function ReasonChips({
  selected,
  onSelect,
  onSkipReason,
  onCancel,
}: ReasonChipsProps) {
  return (
    <div>
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl tracking-tight text-ink-text">Why not interested?</h2>
          <p className="mt-1 text-sm text-muted">
            Optional feedback helps refine your matches.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={onCancel}>
          Back
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {LEFT_SWIPE_REASONS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            onClick={() => onSelect(value)}
            className={`rounded-[var(--radius-button)] border px-4 py-3 text-left text-sm font-medium transition ${
              selected === value
                ? "border-brand/30 bg-brand-muted text-brand-strong ring-1 ring-brand/10"
                : "border-border bg-surface-raised text-ink-text hover:border-muted hover:bg-surface-overlay"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <Button variant="secondary" fullWidth size="lg" className="mt-4" onClick={onSkipReason}>
        Continue without reason
      </Button>
    </div>
  );
}
