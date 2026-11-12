import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import {
  ApplicationStepsPanel,
  saveApplicationStepTemplate,
} from "../components/ApplicationStepsPanel";
import { AddJobByUrlCard } from "../components/AddJobByUrlCard";
import { JobQueueCard } from "../components/JobQueueCard";
import { Button } from "../components/ui/Button";
import { Chip } from "../components/ui/Chip";
import { Alert, EmptyState } from "../components/ui/Alert";
import { PageHeader } from "../components/ui/PageHeader";
import { useEngagement } from "../hooks/useEngagement";
import { isPacketPrepared } from "../lib/packetPrep";
import type { ApplicationStep, TodoItem, TodoStatus } from "../types";

const TABS: { key: TodoStatus | "all"; label: string }[] = [
  { key: "to_apply", label: "To apply" },
  { key: "applied", label: "Applied" },
  { key: "archived", label: "Archived" },
  { key: "all", label: "All" },
];

export function TodoListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { engagement, refresh: refreshEngagement } = useEngagement();
  const [items, setItems] = useState<TodoItem[]>([]);
  const [tab, setTab] = useState<TodoStatus | "all">("to_apply");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [promptId, setPromptId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [savingItemId, setSavingItemId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.todo.list(tab === "all" ? undefined : tab);
      setItems(res.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const prompt = searchParams.get("prompt");
    if (prompt) {
      setPromptId(prompt);
      setExpandedId(prompt);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  function handleApply(item: TodoItem) {
    void api.engagement.heartbeat("prepare_open").catch(() => undefined);
    if (item.packet_id && isPacketPrepared(item.packet_status ?? "none")) {
      navigate(`/applications/${item.packet_id}`);
      return;
    }
    navigate(`/todo/${item.id}/prepare`);
  }

  async function handleMarkApplied(itemId: string) {
    setSavingItemId(itemId);
    setError(null);
    try {
      await api.todo.markApplied(itemId);
      void api.engagement.heartbeat("mark_applied").catch(() => undefined);
      void refreshEngagement();
      setPromptId(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to mark as applied");
    } finally {
      setSavingItemId(null);
    }
  }

  async function handleMoveBackToApply(itemId: string) {
    setSavingItemId(itemId);
    setError(null);
    try {
      await api.todo.update(itemId, { status: "to_apply" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update status");
    } finally {
      setSavingItemId(null);
    }
  }

  async function handleSelfReport(itemId: string, didApply: boolean) {
    try {
      await api.todo.selfReport(itemId, didApply);
      if (didApply) {
        void api.engagement.heartbeat("mark_applied").catch(() => undefined);
        void refreshEngagement();
      }
      setPromptId(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save");
    }
  }

  async function handleArchive(itemId: string) {
    try {
      await api.todo.update(itemId, { status: "archived" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to archive");
    }
  }

  async function handleStepsChange(itemId: string, steps: ApplicationStep[]) {
    setSavingItemId(itemId);
    setError(null);
    try {
      const updated = await api.todo.updateSteps(itemId, steps);
      setItems((current) => current.map((item) => (item.id === itemId ? updated : item)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save steps");
    } finally {
      setSavingItemId(null);
    }
  }

  const toApplyCount = items.filter((i) => i.status === "to_apply").length;
  const appliedCount = items.filter((i) => i.status === "applied").length;
  const preparedCount = items.filter((i) =>
    ["ready", "opened", "applied"].includes(i.packet_status ?? "none"),
  ).length;
  const pendingPrepCount = items.filter(
    (i) => (i.packet_status ?? "none") === "none" && i.status === "to_apply",
  ).length;

  return (
    <div className="pb-2">
      <PageHeader
        title="Application queue"
        subtitle="Prepare applications, track progress, and mark jobs as applied when you're done."
      />

      <div className="mt-3">
        <AddJobByUrlCard onError={setError} />
      </div>

      {engagement ? (
        <p className="mt-3 text-sm text-muted">
          <span className="font-semibold text-ink-text">{engagement.in_prep_count}</span> ready to
          apply ·{" "}
          <span className="font-semibold text-ink-text">{engagement.applied_this_week}</span> applied
          this week
          {preparedCount > 0 || pendingPrepCount > 0 ? (
            <>
              {" "}
              · <span className="font-semibold text-ink-text">{preparedCount}</span> AI-prepped
              {pendingPrepCount > 0 ? (
                <>
                  {" "}
                  · <span className="font-semibold text-accent-strong">{pendingPrepCount}</span>{" "}
                  awaiting prep
                </>
              ) : null}
            </>
          ) : null}
          {" · "}
          <Link
            to="/applications"
            className="font-semibold text-brand-strong hover:text-brand-deep"
          >
            Your applications
          </Link>
        </p>
      ) : (
        <p className="mt-3 text-sm">
          <Link
            to="/applications"
            className="font-semibold text-brand-strong hover:text-brand-deep"
          >
            Your applications
          </Link>
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {TABS.map(({ key, label }) => (
          <Chip key={key} active={tab === key} onClick={() => setTab(key)}>
            {label}
            {key === "to_apply" && toApplyCount > 0 ? ` (${toApplyCount})` : ""}
            {key === "applied" && appliedCount > 0 ? ` (${appliedCount})` : ""}
          </Chip>
        ))}
      </div>

      {error ? (
        <Alert tone="error" className="mt-4">
          {error}
        </Alert>
      ) : null}

      {loading ? (
        <p className="mt-10 text-center text-muted">Loading your queue…</p>
      ) : items.length === 0 ? (
        <EmptyState
          icon={
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M9 11l2 2 4-4"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
              <rect
                x="4"
                y="4"
                width="16"
                height="16"
                rx="3"
                stroke="currentColor"
                strokeWidth="1.75"
              />
            </svg>
          }
          title="Your queue is empty"
          description="Swipe right on matches in the deck, or paste a job URL above to import a posting and start prepping."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Link to="/deck">
                <Button>Go to deck</Button>
              </Link>
            </div>
          }
        />
      ) : (
        <ul className="mt-6 space-y-3">
          {items.map((item) => {
            const isExpanded = expandedId === item.id;
            const isSaving = savingItemId === item.id;
            const steps = item.application_steps ?? [];

            return (
              <li key={item.id}>
                <JobQueueCard
                  item={item}
                  isExpanded={isExpanded}
                  isSaving={isSaving}
                  showPrompt={promptId === item.id}
                  onPrepare={() => handleApply(item)}
                  onMarkApplied={() => void handleMarkApplied(item.id)}
                  onMoveBack={() => void handleMoveBackToApply(item.id)}
                  onArchive={() => void handleArchive(item.id)}
                  onToggleExpand={() => setExpandedId(isExpanded ? null : item.id)}
                  onSelfReport={(didApply) => void handleSelfReport(item.id, didApply)}
                  onStepsChange={(nextSteps) => handleStepsChange(item.id, nextSteps)}
                  stepsPanel={
                    <ApplicationStepsPanel
                      steps={steps}
                      compact
                      disabled={isSaving}
                      onChange={(nextSteps) => handleStepsChange(item.id, nextSteps)}
                      onSaveTemplate={(nextSteps) => saveApplicationStepTemplate(nextSteps)}
                    />
                  }
                />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
