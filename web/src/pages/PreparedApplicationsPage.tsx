import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { PacketPrepBadge } from "../components/PacketPrepBadge";
import { Button } from "../components/ui/Button";
import { Alert, EmptyState, SurfaceCard } from "../components/ui/Alert";
import { PageHeader } from "../components/ui/PageHeader";
import type { PreparedPacketSummary } from "../types";

const FIT_LABELS: Record<NonNullable<PreparedPacketSummary["fit_verdict"]>, string> = {
  apply: "Apply",
  lean_apply: "Lean apply",
  lean_skip: "Lean skip",
  skip: "Skip",
};

function formatUpdated(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function PreparedApplicationsPage() {
  const [items, setItems] = useState<PreparedPacketSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.todo
      .listPrepared()
      .then((res) => setItems(res.items))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="pb-6">
      <PageHeader
        title="Your applications"
        subtitle="Named cover letters and fit summaries you paid to generate. Reuse them on similar jobs."
        action={
          <Link
            to="/todo"
            className="shrink-0 text-sm font-semibold text-brand-strong hover:text-brand-deep"
          >
            ← Application queue
          </Link>
        }
      />

      {error ? (
        <Alert tone="error" className="mt-4">
          {error}
        </Alert>
      ) : null}

      {loading ? (
        <p className="mt-10 text-center text-muted">Loading your applications…</p>
      ) : items.length === 0 ? (
        <EmptyState
          icon={
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M7 4h10v16H7z"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinejoin="round"
              />
              <path d="M9 8h6M9 12h6M9 16h4" stroke="currentColor" strokeWidth="1.75" />
            </svg>
          }
          title="No applications yet"
          description="Prepare a job from your queue to generate a reusable cover letter and fit summary."
          action={
            <Link to="/todo">
              <Button>Go to application queue</Button>
            </Link>
          }
        />
      ) : (
        <ul className="mt-6 space-y-3">
          {items.map((item) => (
            <li key={item.id}>
              <SurfaceCard>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <PacketPrepBadge status={item.status} />
                      {item.fit_verdict ? (
                        <span className="rounded-full border border-border bg-surface-raised px-2 py-0.5 text-[11px] font-medium text-muted">
                          {FIT_LABELS[item.fit_verdict]}
                        </span>
                      ) : null}
                    </div>
                    <h2 className="font-semibold text-ink-text">{item.label || item.title}</h2>
                    <p className="text-sm text-muted">
                      {item.title}
                      {item.company ? ` · ${item.company}` : ""}
                    </p>
                    <p className="mt-2 text-xs text-muted">
                      Updated {formatUpdated(item.updated_at)}
                      {item.has_cover_letter ? " · cover letter" : ""}
                    </p>
                  </div>
                  <Link to={`/applications/${item.id}`}>
                    <Button size="sm">Open report</Button>
                  </Link>
                </div>
              </SurfaceCard>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
