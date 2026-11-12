import { useState } from "react";
import { api, ApiError } from "../api/client";
import { ChatMarkdown } from "./ChatMarkdown";
import { Alert, SurfaceCard } from "./ui/Alert";
import { Button } from "./ui/Button";
import type { ResumeProposal, ResumeProposalOperation } from "../types";

function formatOperation(op: ResumeProposalOperation): string {
  switch (op.type) {
    case "set_identity":
      return "Update contact and identity";
    case "set_summary":
      return `Update summary (${op.summary.length} characters)`;
    case "set_headline":
      return `Set headline: ${op.headline}`;
    case "add_experience":
      return `Add role: ${op.experience.title} at ${op.experience.company_name}`;
    case "update_experience":
      return `Update role: ${op.experience.title}`;
    case "append_highlights":
      return `Add ${op.highlights.length} bullet${op.highlights.length === 1 ? "" : "s"}`;
    case "replace_highlights":
      return `Replace bullets (${op.highlights.length})`;
    case "remove_experience":
      return `Remove experience ${op.experience_id}`;
    case "add_education":
      return `Add education: ${op.education.institution}`;
    case "update_education":
      return `Update education: ${op.education.institution}`;
    case "add_contact_link":
      return `Add link: ${op.link.title || op.link.url}`;
    case "set_skills":
      return `Set skills (${op.skill_names.length})`;
    default:
      return "Resume change";
  }
}

type Props = {
  proposal: ResumeProposal;
  onApplied?: (proposal: ResumeProposal) => void;
  onDismissed?: (proposal: ResumeProposal) => void;
  onEdit?: (proposal: ResumeProposal) => void;
};

export function ResumeProposalCard({ proposal, onApplied, onDismissed, onEdit }: Props) {
  const [busy, setBusy] = useState<"apply" | "dismiss" | null>(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isPending = proposal.status === "pending";

  async function handleApply() {
    if (!isPending || busy) return;
    setBusy("apply");
    setError(null);
    try {
      const res = await api.resume.chat.applyProposal(proposal.id);
      onApplied?.(res.proposal);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to apply changes");
    } finally {
      setBusy(null);
    }
  }

  async function handleDismiss() {
    if (!isPending || busy) return;
    setBusy("dismiss");
    setError(null);
    try {
      const res = await api.resume.chat.rejectProposal(proposal.id);
      onDismissed?.(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to dismiss proposal");
    } finally {
      setBusy(null);
    }
  }

  function handleEdit() {
    setEditing((v) => !v);
    onEdit?.(proposal);
  }

  return (
    <SurfaceCard padding="sm" className="border-brand/20 bg-brand/5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-brand-strong">
          Suggested resume changes
        </p>
        {!isPending ? (
          <span className="shrink-0 rounded-full border border-border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted">
            {proposal.status}
          </span>
        ) : null}
      </div>

      <div className="mt-2 text-sm text-ink-text">
        <ChatMarkdown content={proposal.preview_summary} />
      </div>

      {editing && proposal.operations.length > 0 ? (
        <ul className="mt-3 space-y-1 rounded-[var(--radius-button)] border border-border bg-surface px-3 py-2 text-xs text-muted">
          {proposal.operations.map((op, idx) => (
            <li key={`${proposal.id}-op-${idx}`}>{formatOperation(op)}</li>
          ))}
        </ul>
      ) : null}

      {error ? <Alert tone="error" className="mt-2">{error}</Alert> : null}

      {isPending ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" size="sm" disabled={busy !== null} onClick={() => void handleApply()}>
            {busy === "apply" ? "Applying…" : "Apply"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy !== null}
            onClick={handleEdit}
          >
            {editing ? "Hide details" : "Edit"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy !== null}
            onClick={() => void handleDismiss()}
          >
            {busy === "dismiss" ? "Dismissing…" : "Dismiss"}
          </Button>
        </div>
      ) : null}
    </SurfaceCard>
  );
}
