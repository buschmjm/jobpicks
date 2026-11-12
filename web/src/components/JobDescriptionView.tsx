import type { MouseEvent } from "react";
import { DiscussWithAdvisorButton } from "./DiscussWithAdvisorButton";
import { JobDescription } from "./JobDescription";
import { InlineSpinner } from "./ui/NavIcon";
import { useJobDescription } from "../hooks/useJobDescription";
import { openApplicationUrl } from "../lib/openApplicationUrl";
import type { MatchCard as MatchCardType } from "../types";

interface JobDescriptionViewProps {
  card: MatchCardType;
  className?: string;
  showHeader?: boolean;
  headerTitleId?: string;
  showDiscussButton?: boolean;
  /** Called before navigating to advisor (e.g. close modal). */
  onDiscussNavigating?: () => void;
}

/** Shared job description body for modal and desktop detail pane. */
export function JobDescriptionView({
  card,
  className = "",
  showHeader = false,
  headerTitleId,
  showDiscussButton = true,
  onDiscussNavigating,
}: JobDescriptionViewProps) {
  const { description, truncated, loading } = useJobDescription(card.job_id, card.description);

  async function handleOpenPosting(e: MouseEvent) {
    e.preventDefault();
    openApplicationUrl(card.source_url);
  }

  return (
    <div className={className}>
      {showHeader ? (
        <div className="mb-4">
          <h2
            id={headerTitleId}
            className="text-lg font-semibold leading-snug text-ink-text"
          >
            {card.title}
          </h2>
          <p className="mt-0.5 text-sm font-medium text-muted">{card.company}</p>
        </div>
      ) : null}
      {loading ? (
        <div className="mb-3 flex items-center gap-2 text-sm text-muted">
          <InlineSpinner label="Loading full description" />
          Loading full description…
        </div>
      ) : null}
      <JobDescription text={description} />
      {truncated ? (
        <p className="mt-4 text-sm text-muted">
          This posting preview is shortened. Use “View original posting” for the complete job
          description.
        </p>
      ) : null}
      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        {showDiscussButton ? (
          <DiscussWithAdvisorButton card={card} onNavigating={onDiscussNavigating} />
        ) : null}
        <button
          type="button"
          onClick={handleOpenPosting}
          className="inline-flex items-center gap-1 text-sm font-semibold text-brand-strong hover:text-brand-deep"
        >
          View original posting →
        </button>
      </div>
    </div>
  );
}
