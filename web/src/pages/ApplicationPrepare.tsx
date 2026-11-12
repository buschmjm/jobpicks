import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Button } from "../components/ui/Button";
import { Alert, SurfaceCard } from "../components/ui/Alert";
import { InlineSpinner, LoadingSpinner } from "../components/ui/NavIcon";
import { PageHeader } from "../components/ui/PageHeader";
import { ApplicationAssistPanel } from "../components/ApplicationAssistPanel";
import { ApplicationReport } from "../components/ApplicationReport";
import { UpgradeProCTA } from "../components/UpgradeProCTA";
import {
  ApplicationStepsPanel,
  saveApplicationStepTemplate,
} from "../components/ApplicationStepsPanel";
import { copyText, formatApplicationKit } from "../lib/applicationKit";
import { openApplicationUrl } from "../lib/openApplicationUrl";
import { canOpenApplication, packetActionLabel } from "../lib/packetPrep";
import type {
  ApplicationPacket,
  ApplicationStep,
  BillingStatus,
  PreparedPacketSummary,
  TodoItem,
} from "../types";

export function ApplicationPreparePage() {
  const { todoId } = useParams<{ todoId: string }>();
  const navigate = useNavigate();
  const [packet, setPacket] = useState<ApplicationPacket | null>(null);
  const [todoItem, setTodoItem] = useState<TodoItem | null>(null);
  const [coverLetter, setCoverLetter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [opening, setOpening] = useState(false);
  const [savingCover, setSavingCover] = useState(false);
  const [kitCopied, setKitCopied] = useState(false);
  const [generatingSince, setGeneratingSince] = useState<number | null>(null);
  const [retryingGeneration, setRetryingGeneration] = useState(false);
  const [savingSteps, setSavingSteps] = useState(false);
  const [markingApplied, setMarkingApplied] = useState(false);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [packetLimitReached, setPacketLimitReached] = useState(false);
  const [library, setLibrary] = useState<PreparedPacketSummary[]>([]);
  const [reuseId, setReuseId] = useState("");
  const [reusing, setReusing] = useState(false);

  const applyPacket = useCallback((next: ApplicationPacket) => {
    setPacket(next);
    setCoverLetter(next.cover_letter ?? "");
  }, []);

  const loadOrGenerate = useCallback(async () => {
    if (!todoId) return;
    setLoading(true);
    setError(null);
    setPacketLimitReached(false);
    try {
      const billingStatus = await api.billing.status().catch(() => null);
      setBilling(billingStatus);

      const atPacketLimit =
        billingStatus?.tier === "free" &&
        billingStatus.lifetime_packets_limit != null &&
        billingStatus.lifetime_packets_used >= billingStatus.lifetime_packets_limit;

      const [todo, packetResult] = await Promise.allSettled([
        api.todo.get(todoId),
        (async () => {
          try {
            return await api.todo.getPacket(todoId);
          } catch (err) {
            if (err instanceof ApiError && err.status === 404) {
              if (atPacketLimit) {
                setPacketLimitReached(true);
                return null;
              }
              return await api.todo.generatePacket(todoId);
            }
            throw err;
          }
        })(),
      ]);

      if (todo.status === "fulfilled" && todo.value) {
        setTodoItem(todo.value);
      }
      if (packetResult.status === "fulfilled" && packetResult.value) {
        applyPacket(packetResult.value);
      } else if (packetResult.status === "rejected") {
        throw packetResult.reason;
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setPacketLimitReached(true);
        setError(null);
        return;
      }
      setError(err instanceof ApiError ? err.message : "Failed to load application packet");
    } finally {
      setLoading(false);
    }
  }, [applyPacket, todoId]);

  useEffect(() => {
    void loadOrGenerate();
    void api.engagement.heartbeat("prepare_open").catch(() => undefined);
    void api.todo
      .listPrepared()
      .then((res) => setLibrary(res.items))
      .catch(() => undefined);
  }, [loadOrGenerate]);

  useEffect(() => {
    if (packet?.status === "generating") {
      setGeneratingSince((prev) => prev ?? Date.now());
      return;
    }
    setGeneratingSince(null);
    setRetryingGeneration(false);
  }, [packet?.status]);

  useEffect(() => {
    if (!todoId || packet?.status !== "generating") return;

    const retry = async () => {
      setRetryingGeneration(true);
      try {
        const next = await api.todo.generatePacket(todoId);
        applyPacket(next);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to retry packet generation");
      } finally {
        setRetryingGeneration(false);
      }
    };

    const intervalId = window.setInterval(() => {
      void retry();
    }, 45_000);

    return () => window.clearInterval(intervalId);
  }, [applyPacket, packet?.status, todoId]);

  useEffect(() => {
    if (!todoId || !packet || packet.status !== "generating") return;

    const intervalId = window.setInterval(() => {
      void (async () => {
        try {
          const next = await api.todo.getPacket(todoId);
          applyPacket(next);
        } catch (err) {
          setError(err instanceof ApiError ? err.message : "Failed to refresh packet");
        }
      })();
    }, 2000);

    return () => window.clearInterval(intervalId);
  }, [applyPacket, packet?.status, todoId]);

  async function saveCoverLetter(nextCover: string) {
    if (!todoId) return null;
    setSavingCover(true);
    try {
      const updated = await api.todo.patchPacket(todoId, {
        cover_letter: nextCover || null,
      });
      applyPacket(updated);
      return updated;
    } finally {
      setSavingCover(false);
    }
  }

  async function handleCoverLetterBlur() {
    if (!packet || !todoId) return;
    if ((packet.cover_letter ?? "") === coverLetter) return;
    try {
      await saveCoverLetter(coverLetter);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save cover letter");
    }
  }

  async function handleRegenerate() {
    if (!todoId) return;
    setRegenerating(true);
    setError(null);
    try {
      const next = await api.todo.generatePacket(todoId);
      applyPacket(next);
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setPacketLimitReached(true);
        setError(null);
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to regenerate packet");
      }
    } finally {
      setRegenerating(false);
    }
  }

  async function handleReuse() {
    if (!todoId || !reuseId) return;
    setReusing(true);
    setError(null);
    try {
      const next = await api.todo.reusePacket(todoId, reuseId);
      applyPacket(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to reuse application");
    } finally {
      setReusing(false);
    }
  }

  async function handleOpenApplication() {
    if (!packet || !todoId) return;
    setOpening(true);
    setError(null);
    try {
      await api.todo.patchPacket(todoId, {
        cover_letter: coverLetter || null,
      });
      const opened = await api.todo.openPacket(todoId);
      openApplicationUrl(opened.apply_url);
      navigate(`/todo?prompt=${todoId}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to open application");
      setOpening(false);
    }
  }

  async function handleStepsChange(steps: ApplicationStep[]) {
    if (!todoId) return;
    setSavingSteps(true);
    setError(null);
    try {
      const updated = await api.todo.updateSteps(todoId, steps);
      setTodoItem(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save progress");
    } finally {
      setSavingSteps(false);
    }
  }

  async function handleMarkApplied() {
    if (!todoId) return;
    setMarkingApplied(true);
    setError(null);
    try {
      const updated = await api.todo.markApplied(todoId);
      void api.engagement.heartbeat("mark_applied").catch(() => undefined);
      setTodoItem(updated);
      navigate("/todo");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to mark as applied");
    } finally {
      setMarkingApplied(false);
    }
  }

  async function handleCopyKit() {
    if (!packet) return;
    try {
      await copyText(formatApplicationKit(packet, coverLetter));
      setKitCopied(true);
      window.setTimeout(() => setKitCopied(false), 2000);
    } catch {
      setError("Could not copy cover letter");
    }
  }

  const isGenerating = packet?.status === "generating";
  const isReady = canOpenApplication(packet);
  const showPacketActions = !loading && !packetLimitReached;
  const packetActionBusy = regenerating || isGenerating;
  const reusableApps = library.filter((item) => item.id !== packet?.id);
  const pageTitle = todoItem
    ? `${todoItem.company} · Application prep`
    : "Application prep";

  return (
    <div className="pb-24">
      <PageHeader
        title={pageTitle}
        subtitle="Generate or reuse a cover letter for this job, then track whether you submitted it."
        action={
          <Link
            to="/applications"
            className="shrink-0 text-sm font-semibold text-brand-strong hover:text-brand-deep"
          >
            Your applications
          </Link>
        }
      />

      {error ? <Alert tone="error">{error}</Alert> : null}

      {packetLimitReached && billing?.lifetime_packets_limit != null ? (
        <UpgradeProCTA
          className="mt-4"
          used={billing.lifetime_packets_used}
          limit={billing.lifetime_packets_limit}
          stripeConfigured={billing.stripe_configured}
          externalCheckoutAllowed={billing.external_checkout_allowed}
        />
      ) : null}

      {!packetLimitReached &&
      billing?.tier === "free" &&
      billing.lifetime_packets_limit != null &&
      billing.lifetime_packets_used === billing.lifetime_packets_limit - 1 ? (
        <Alert tone="info" className="mt-4">
          <p className="text-sm">
            You have 1 free AI application packet left.{" "}
            <Link to="/settings" className="font-semibold text-brand-strong hover:text-brand-deep">
              Upgrade to Pro
            </Link>{" "}
            for 20 AI application packets per month on Pro.
          </p>
        </Alert>
      ) : null}

      {loading && !packet ? (
        <div className="mt-10">
          <LoadingSpinner label="Loading application packet…" />
        </div>
      ) : null}

      {isGenerating ? (
        <SurfaceCard className="mt-4">
          <div className="flex items-center gap-3">
            <InlineSpinner label="" />
            <div>
              <p className="font-semibold text-ink-text">Generating your application</p>
              <p className="mt-1 text-sm text-muted">
                Drafting fit analysis and a tailored cover letter from your profile.
              </p>
              {generatingSince && Date.now() - generatingSince > 45_000 ? (
                <p className="mt-2 text-sm text-muted">
                  {retryingGeneration
                    ? "Retrying generation…"
                    : "This is taking longer than expected. Retrying automatically."}
                </p>
              ) : null}
            </div>
          </div>
        </SurfaceCard>
      ) : null}

      {packet?.status === "failed" ? (
        <Alert tone="error" className="mt-4">
          {packet.generation_error ?? "Packet generation failed. Try again."}
        </Alert>
      ) : null}

      {!packet && !loading && !packetLimitReached && !isGenerating ? (
        <SurfaceCard className="mt-4">
          <p className="font-semibold text-ink-text">No application yet</p>
          <p className="mt-2 text-sm text-muted">
            Generate a fit summary and tailored cover letter for this role, or reuse a letter from
            another application.
          </p>
          <Button className="mt-4" disabled={packetActionBusy} onClick={() => void handleRegenerate()}>
            {packetActionLabel(null, regenerating)}
          </Button>
        </SurfaceCard>
      ) : null}

      {reusableApps.length > 0 && !isGenerating ? (
        <SurfaceCard className="mt-4">
          <p className="text-sm font-semibold text-ink-text">Reuse an existing cover letter</p>
          <p className="mt-1 text-sm text-muted">
            Start from a saved application like Office Manager or Sales Manager, then edit for this
            posting.
          </p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <select
              className="w-full rounded-[var(--radius-button)] border border-border bg-surface px-3 py-2 text-sm text-ink-text"
              value={reuseId}
              onChange={(event) => setReuseId(event.target.value)}
            >
              <option value="">Choose an application…</option>
              {reusableApps.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label || item.title}
                  {item.company ? ` · ${item.company}` : ""}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              variant="secondary"
              disabled={!reuseId || reusing}
              onClick={() => void handleReuse()}
            >
              {reusing ? "Copying…" : "Use this letter"}
            </Button>
          </div>
        </SurfaceCard>
      ) : null}

      {packet && !isGenerating && packet.status !== "failed" ? (
        <div className="mt-4 space-y-4">
          <SurfaceCard>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-ink-text">
                  {packet.label || todoItem?.title || "Generated application"}
                </p>
                <p className="mt-1 text-sm text-muted">
                  Fit summary and cover letter for this role. Edit the letter before you apply.
                </p>
              </div>
              <Link to={`/applications/${packet.id}`}>
                <Button size="sm" variant="secondary">
                  Open application page
                </Button>
              </Link>
            </div>
          </SurfaceCard>

          <ApplicationReport
            packet={packet}
            coverLetter={coverLetter}
            coverDisabled={!isReady || savingCover}
            kitCopied={kitCopied}
            onCopyKit={() => void handleCopyKit()}
            onCoverLetterChange={setCoverLetter}
            onCoverLetterBlur={() => void handleCoverLetterBlur()}
          />

          {todoItem && todoItem.status === "to_apply" ? (
            <SurfaceCard>
              <p className="text-sm font-semibold text-ink-text">Track this job</p>
              <p className="mt-1 text-sm text-muted">
                Applied/not-applied status lives on the queue. These steps are only for this posting.
              </p>
              <div className="mt-3">
                <ApplicationStepsPanel
                  steps={todoItem.application_steps ?? []}
                  disabled={savingSteps}
                  onChange={handleStepsChange}
                  onSaveTemplate={(steps) => saveApplicationStepTemplate(steps)}
                />
              </div>
            </SurfaceCard>
          ) : null}

          {todoId && todoItem ? (
            <SurfaceCard>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-ink-text">Resume for this posting</p>
                  <p className="mt-1 text-sm text-muted">
                    Tailor a resume for {todoItem.title} at {todoItem.company}.
                  </p>
                </div>
                <Link to={`/advisor/build?todo_id=${encodeURIComponent(todoId)}`}>
                  <Button size="sm">Open resume builder</Button>
                </Link>
              </div>
            </SurfaceCard>
          ) : null}

          {todoId ? (
            <SurfaceCard>
              <p className="text-sm font-semibold text-ink-text">Question help</p>
              <div className="mt-3">
                <ApplicationAssistPanel todoId={todoId} />
              </div>
            </SurfaceCard>
          ) : null}

          <SurfaceCard>
            <p className="text-sm font-semibold text-ink-text">Submit this job</p>
            <p className="mt-1 text-sm text-muted">
              Open the employer site, paste your cover letter, then mark applied when you are done.
            </p>
          </SurfaceCard>

          <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-canvas/95 px-4 py-3 backdrop-blur-md sm:static sm:border-0 sm:bg-transparent sm:p-0">
            <div className="mx-auto flex max-w-3xl flex-col gap-2 sm:flex-row sm:flex-wrap">
              {isReady ? (
                <Button
                  fullWidth
                  className="sm:w-auto sm:flex-1"
                  disabled={opening}
                  onClick={() => void handleOpenApplication()}
                >
                  {opening ? "Opening…" : "Open application site"}
                </Button>
              ) : null}
              {todoItem?.status === "to_apply" && isReady ? (
                <Button
                  fullWidth
                  variant="success"
                  className="sm:w-auto"
                  disabled={markingApplied}
                  onClick={() => void handleMarkApplied()}
                >
                  {markingApplied ? "Saving…" : "Mark as applied"}
                </Button>
              ) : null}
              <Button
                fullWidth
                variant="secondary"
                className="sm:w-auto"
                disabled={packetActionBusy}
                onClick={() => void handleRegenerate()}
              >
                {packetActionLabel(packet, regenerating)}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {showPacketActions && packet?.status === "failed" ? (
        <div className="mt-4">
          <Button variant="secondary" disabled={regenerating} onClick={() => void handleRegenerate()}>
            {packetActionLabel(packet, regenerating)}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
