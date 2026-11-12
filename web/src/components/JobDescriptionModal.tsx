import { useEffect } from "react";
import { createPortal } from "react-dom";
import { DiscussWithAdvisorButton } from "./DiscussWithAdvisorButton";
import { JobDescription } from "./JobDescription";
import { InlineSpinner } from "./ui/NavIcon";
import { useJobDescription } from "../hooks/useJobDescription";
import { openApplicationUrl } from "../lib/openApplicationUrl";
import type { MatchCard as MatchCardType } from "../types";

interface JobDescriptionModalProps {
  card: MatchCardType;
  onClose: () => void;
}

export function JobDescriptionModal({ card, onClose }: JobDescriptionModalProps) {
  const { description, truncated, loading } = useJobDescription(card.job_id, card.description);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="job-description-title"
    >
      <button
        type="button"
        className="absolute inset-0 bg-ink-text/40 backdrop-blur-[2px]"
        aria-label="Close job description"
        onClick={onClose}
      />

      <div className="relative mx-auto flex h-[92dvh] w-full max-w-lg min-h-0 flex-col overflow-hidden rounded-t-[var(--radius-card)] border border-border bg-surface shadow-[0_-12px_40px_rgba(15,23,42,0.18)] sm:h-auto sm:max-h-[min(88vh,720px)] sm:rounded-[var(--radius-card)] sm:shadow-[0_20px_50px_-12px_rgba(15,23,42,0.25)]">
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border-subtle px-4 py-3 sm:px-5 sm:py-4">
          <div className="min-w-0 pr-2">
            <p className="text-xs font-semibold uppercase tracking-[0.06em] text-subtle">
              Job description
            </p>
            <h2
              id="job-description-title"
              className="mt-1 text-lg font-semibold leading-snug text-ink-text"
            >
              {card.title}
            </h2>
            <p className="mt-0.5 text-sm font-medium text-muted">{card.company}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border bg-surface-raised text-lg leading-none text-muted transition hover:border-muted hover:text-ink-text"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-5 sm:py-5"
          style={{ WebkitOverflowScrolling: "touch" }}
        >
          {loading ? (
            <div className="mb-3 flex items-center gap-2 text-sm text-muted">
              <InlineSpinner label="Loading full description" />
              Loading full description…
            </div>
          ) : null}
          <JobDescription text={description} />
          {truncated ? (
            <p className="mt-4 text-sm text-muted">
              This posting preview is shortened. Use “View original posting” below for the complete
              job description.
            </p>
          ) : null}
        </div>

        <div className="shrink-0 space-y-3 border-t border-border-subtle bg-surface px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-5">
          <DiscussWithAdvisorButton card={card} onNavigating={onClose} fullWidth />
          <button
            type="button"
            onClick={() => openApplicationUrl(card.source_url)}
            className="inline-flex w-full items-center justify-center gap-1 text-sm font-semibold text-brand-strong hover:text-brand-deep"
          >
            View original posting →
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
