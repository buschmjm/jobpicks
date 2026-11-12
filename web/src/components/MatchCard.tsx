import { useState, type ReactNode } from "react";
import type { MatchCard as MatchCardType, WorkMode } from "../types";
import { JobDescriptionModal } from "./JobDescriptionModal";
import { Button } from "./ui/Button";

interface MatchCardProps {
  card: MatchCardType;
  onDetailsOpenChange?: (open: boolean) => void;
  showActions?: boolean;
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  onSkip?: () => void;
  dragOffset?: { x: number; y: number };
  isDragging?: boolean;
  compact?: boolean;
}

function workModeLabel(mode: WorkMode): string {
  switch (mode) {
    case "remote":
      return "Remote";
    case "hybrid":
      return "Hybrid";
    case "onsite":
      return "On-site";
    default:
      return "Location varies";
  }
}

function workModeClasses(mode: WorkMode): string {
  switch (mode) {
    case "remote":
      return "border-emerald-200 bg-success-muted text-success";
    case "hybrid":
      return "border-indigo-200 bg-indigo-50 text-explore";
    case "onsite":
      return "border-stone-200 bg-stone-100 text-muted";
    default:
      return "border-border bg-surface-raised text-muted";
  }
}

function MetaPill({
  children,
  className = "border-border bg-surface-raised text-muted",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-lg border px-2.5 py-1 text-xs font-medium ${className}`}
    >
      {children}
    </span>
  );
}

function matchScoreClasses(score: number): string {
  if (score >= 80) return "border-accent/30 bg-accent-muted text-accent-strong";
  if (score >= 60) return "border-stone-200 bg-stone-100 text-muted";
  return "border-border bg-surface-raised text-subtle";
}

const CRITERION_LABELS: Record<string, string> = {
  semantic: "Profile fit",
  skill: "Skills overlap",
  title: "Title alignment",
  level: "Seniority fit",
  comp: "Compensation fit",
  geo: "Location fit",
  facets: "Learned preferences",
};

const HIDDEN_BREAKDOWN_KEYS = new Set([
  "match_score",
  "attainability",
  "deck_rank_score",
  "level_delta",
  "stretch",
  "qual_penalty",
]);

function stripCriterionPercent(text: string): string {
  return text.replace(/\s*\(\d+%\)\s*$/g, "").trim();
}

function matchingCriteria(breakdown: Record<string, number> | null | undefined): string[] {
  if (!breakdown) return [];
  return Object.entries(breakdown)
    .filter(([key, value]) => !HIDDEN_BREAKDOWN_KEYS.has(key) && typeof value === "number")
    .sort((a, b) => b[1] - a[1])
    .map(([key]) => CRITERION_LABELS[key] ?? key.replace(/_/g, " "));
}

export function MatchCard({
  card,
  onDetailsOpenChange,
  showActions = true,
  onSwipeLeft,
  onSwipeRight,
  onSkip,
  dragOffset = { x: 0, y: 0 },
  isDragging = false,
  compact = false,
}: MatchCardProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  const openDetails = () => {
    setDetailsOpen(true);
    onDetailsOpenChange?.(true);
  };

  const closeDetails = () => {
    setDetailsOpen(false);
    onDetailsOpenChange?.(false);
  };

  const rotate = dragOffset.x * 0.06;
  const opacity = isDragging ? 0.98 : 1;
  const likeOpacity = Math.min(Math.max(dragOffset.x / 120, 0), 1);
  const nopeOpacity = Math.min(Math.max(-dragOffset.x / 120, 0), 1);
  const salaryListed = !card.salary_display.toLowerCase().includes("not listed");
  const criteria = matchingCriteria(card.score_breakdown);

  return (
    <article
      className={`job-card relative flex flex-col overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface shadow-[0_8px_32px_-12px_rgba(15,23,42,0.12)] ${
        compact ? "" : "min-h-[420px] sm:min-h-[480px]"
      }`}
      style={{
        transform: `translate(${dragOffset.x}px, ${dragOffset.y}px) rotate(${rotate}deg)`,
        opacity,
        transition: isDragging ? "none" : "transform 0.25s ease, opacity 0.25s ease",
      }}
    >
      <div className="h-0.5 bg-gradient-to-r from-accent/60 via-accent to-accent-strong/80" />

      {likeOpacity > 0.05 && (
        <div
          className="pointer-events-none absolute left-4 top-8 z-10 rotate-[-10deg] rounded-lg border-2 border-accent px-3 py-1 text-xl font-bold uppercase tracking-[0.12em] text-accent"
          style={{ opacity: likeOpacity }}
        >
          Interested
        </div>
      )}
      {nopeOpacity > 0.05 && (
        <div
          className="pointer-events-none absolute right-4 top-8 z-10 rotate-[10deg] rounded-lg border-2 border-decline px-3 py-1 text-xl font-bold uppercase tracking-[0.12em] text-decline"
          style={{ opacity: nopeOpacity }}
        >
          Pass
        </div>
      )}

      {card.is_explore && (
        <div className="border-b border-indigo-100 bg-indigo-50 px-4 py-1.5 text-center text-xs font-semibold uppercase tracking-[0.06em] text-explore">
          Explore pick — outside your usual pattern
        </div>
      )}

      {card.stretch && !card.is_explore && (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-center text-xs font-semibold uppercase tracking-[0.06em] text-accent-strong">
          Stretch role — a reach worth considering
        </div>
      )}

      <div className={`flex flex-1 flex-col ${compact ? "p-4" : "p-5 sm:p-6"}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h2
              className={`font-semibold leading-tight text-ink-text ${
                compact ? "text-lg" : "text-xl sm:text-2xl"
              }`}
            >
              {card.title}
            </h2>
            <p className="mt-1 text-base font-medium text-muted">{card.company}</p>
          </div>
          <span
            className={`shrink-0 rounded-xl border px-2.5 py-1.5 text-sm font-bold tabular-nums ${matchScoreClasses(card.match_score)}`}
          >
            {card.match_score}%
          </span>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <MetaPill
            className={
              salaryListed
                ? "border-stone-200 bg-stone-50 text-ink-text"
                : "border-border bg-surface-raised text-subtle"
            }
          >
            {salaryListed ? card.salary_display : "Pay not listed"}
          </MetaPill>
          <MetaPill className={workModeClasses(card.work_mode)}>
            {workModeLabel(card.work_mode)}
          </MetaPill>
          {card.location_display ? (
            <MetaPill>{card.location_display}</MetaPill>
          ) : null}
          {card.commute_display ? (
            <MetaPill className="border-stone-200 bg-stone-50 text-muted">{card.commute_display}</MetaPill>
          ) : null}
          <MetaPill className="border-border-subtle bg-surface-raised/80 text-subtle">
            {card.posted_ago}
          </MetaPill>
        </div>

        <p className="mt-2 text-xs uppercase tracking-[0.06em] text-subtle">Source · {card.source}</p>

        {card.why_bullets.length > 0 && (
          <div className="mt-4 rounded-[var(--radius-button)] border border-accent/20 bg-accent-muted/50 p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-accent-strong">
                Why it fits
              </p>
              <p className="text-xs font-semibold tabular-nums text-accent-strong">
                Fit score {card.match_score}
              </p>
            </div>
            <ul className="mt-2 space-y-1.5">
              {card.why_bullets.slice(0, compact ? 2 : 3).map((b) => (
                <li key={b} className="text-sm leading-snug text-ink-text">
                  {stripCriterionPercent(b)}
                </li>
              ))}
            </ul>
            {criteria.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {criteria.map((label) => (
                  <span
                    key={label}
                    className="rounded-lg border border-accent/20 bg-surface px-2 py-0.5 text-xs font-medium text-muted"
                  >
                    {label}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        )}

        {card.caution_bullets.length > 0 && (
          <div className="mt-3 rounded-[var(--radius-button)] border border-amber-200 bg-amber-50 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-accent-strong">
              Heads up
            </p>
            <ul className="mt-2 space-y-1.5">
              {card.caution_bullets.slice(0, compact ? 1 : 2).map((b) => (
                <li key={b} className="text-sm leading-snug text-ink-text">
                  {stripCriterionPercent(b)}
                </li>
              ))}
            </ul>
          </div>
        )}

        {card.why_bullets.length === 0 && criteria.length > 0 ? (
          <div className="mt-4 rounded-[var(--radius-button)] border border-accent/20 bg-accent-muted/50 p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-accent-strong">
                Why it fits
              </p>
              <p className="text-xs font-semibold tabular-nums text-accent-strong">
                Fit score {card.match_score}
              </p>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {criteria.map((label) => (
                <span
                  key={label}
                  className="rounded-lg border border-accent/20 bg-surface px-2 py-0.5 text-xs font-medium text-muted"
                >
                  {label}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-auto pt-4" data-no-swipe>
          <Button
            variant="secondary"
            fullWidth
            onClick={(e) => {
              e.stopPropagation();
              openDetails();
            }}
          >
            Read job description
          </Button>
        </div>
      </div>

      {detailsOpen ? <JobDescriptionModal card={card} onClose={closeDetails} /> : null}

      {showActions && (
        <div
          className="grid grid-cols-3 gap-2 border-t border-border-subtle bg-surface-raised/80 p-3"
          data-no-swipe
        >
          <button
            type="button"
            onClick={onSwipeLeft}
            className="rounded-[var(--radius-button)] border border-decline/40 bg-surface py-2.5 text-sm font-semibold text-decline transition hover:border-decline hover:bg-surface-overlay active:scale-[0.98]"
            aria-label="Not interested"
          >
            Pass
          </button>
          <button
            type="button"
            onClick={onSkip}
            className="rounded-[var(--radius-button)] border border-border bg-surface py-2.5 text-sm font-semibold text-muted transition hover:bg-surface-overlay active:scale-[0.98]"
            aria-label="Skip"
          >
            Skip
          </button>
          <button
            type="button"
            onClick={onSwipeRight}
            className="rounded-[var(--radius-button)] border border-accent/30 bg-accent-muted py-2.5 text-sm font-semibold text-accent-strong transition hover:bg-amber-100 active:scale-[0.98]"
            aria-label="Interested"
          >
            Interested
          </button>
        </div>
      )}
    </article>
  );
}

interface SwipeActionBarProps {
  onPass: () => void;
  onSkip: () => void;
  onLike: () => void;
  disabled?: boolean;
}

export function SwipeActionBar({ onPass, onSkip, onLike, disabled }: SwipeActionBarProps) {
  return (
    <div className="flex items-center justify-center gap-5 sm:gap-8" data-no-swipe>
      <button
        type="button"
        onClick={onPass}
        disabled={disabled}
        aria-label="Pass"
        className="flex h-14 w-14 items-center justify-center rounded-full border-2 border-decline/50 bg-surface text-xl font-bold text-decline shadow-[0_4px_16px_-6px_rgba(15,23,42,0.15)] transition hover:scale-105 hover:border-decline hover:bg-surface-raised active:scale-95 disabled:opacity-40 sm:h-16 sm:w-16"
      >
        ✕
      </button>
      <button
        type="button"
        onClick={onSkip}
        disabled={disabled}
        aria-label="Skip for now"
        className="flex h-11 w-11 items-center justify-center rounded-full border-2 border-border bg-surface text-lg text-muted shadow-md transition hover:scale-105 hover:bg-surface-raised active:scale-95 disabled:opacity-40"
      >
        ↓
      </button>
      <button
        type="button"
        onClick={onLike}
        disabled={disabled}
        aria-label="Interested"
        className="flex h-14 w-14 items-center justify-center rounded-full border-2 border-accent/40 bg-surface text-xl font-bold text-accent-strong shadow-[0_4px_16px_-6px_rgba(180,83,9,0.2)] transition hover:scale-105 hover:border-accent hover:bg-accent-muted active:scale-95 disabled:opacity-40 sm:h-16 sm:w-16"
      >
        ✓
      </button>
    </div>
  );
}
