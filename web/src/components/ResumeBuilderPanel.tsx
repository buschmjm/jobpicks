import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";
import type { MatchCard, ResumeDocument, ResumeDraft } from "../types";

const LAST_JOB_KEY = "jobdeck.lastDiscussJob";

export function rememberDiscussJob(card: MatchCard) {
  try {
    sessionStorage.setItem(LAST_JOB_KEY, JSON.stringify(card));
  } catch {
    /* ignore */
  }
}

function loadRememberedJob(): MatchCard | null {
  try {
    const raw = sessionStorage.getItem(LAST_JOB_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as MatchCard;
  } catch {
    return null;
  }
}

function toggleRole(doc: ResumeDocument, experienceId: string, included: boolean): ResumeDocument {
  return {
    ...doc,
    roles: (doc.roles || []).map((role) =>
      role.experience_id === experienceId ? { ...role, included } : role,
    ),
  };
}

function toggleHighlight(
  doc: ResumeDocument,
  experienceId: string,
  highlightIndex: number,
  included: boolean,
): ResumeDocument {
  return {
    ...doc,
    roles: (doc.roles || []).map((role) => {
      if (role.experience_id !== experienceId) return role;
      return {
        ...role,
        highlights: role.highlights.map((h, idx) =>
          idx === highlightIndex ? { ...h, included } : h,
        ),
      };
    }),
  };
}

function toggleSkill(
  doc: ResumeDocument,
  groupIndex: number,
  itemIndex: number,
  included: boolean,
): ResumeDocument {
  return {
    ...doc,
    skill_groups: (doc.skill_groups || []).map((group, gi) => {
      if (gi !== groupIndex) return group;
      return {
        ...group,
        items: group.items.map((item, ii) => (ii === itemIndex ? { ...item, included } : item)),
      };
    }),
  };
}

export function ResumeBuilderPanel({
  seedJob = null,
  variant = "collapsible",
}: {
  seedJob?: MatchCard | null;
  variant?: "collapsible" | "page";
}) {
  const isPage = variant === "page";
  const [open, setOpen] = useState(isPage || Boolean(seedJob));
  const [job, setJob] = useState<MatchCard | null>(seedJob);
  const [draft, setDraft] = useState<ResumeDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (seedJob) {
      setJob(seedJob);
      rememberDiscussJob(seedJob);
      setOpen(true);
      return;
    }
    if (!job) setJob(loadRememberedJob());
  }, [seedJob, job]);

  useEffect(() => {
    if (!error) return;
    const node = alertRef.current;
    if (!node) return;
    const scroller = node.closest(".overflow-y-auto");
    if (scroller instanceof HTMLElement) {
      scroller.scrollTo({ top: 0, behavior: "smooth" });
    }
    node.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [error]);

  function showError(err: unknown, fallback: string) {
    setInfo(null);
    setError(err instanceof ApiError ? err.message : fallback);
  }

  async function buildMaster() {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await api.resume.buildMaster();
      setDraft(res);
      setInfo("Full resume draft built from your saved profile. Toggle items, then preview.");
    } catch (err) {
      showError(err, "Failed to build resume");
    } finally {
      setBusy(false);
    }
  }

  async function tailorForJob() {
    if (!job) {
      setError("Discuss a job from the deck first, then tailor for it here.");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await api.resume.tailor({
        job_id: job.job_id,
        title: job.title,
        company: job.company,
        description: job.description,
        source_url: job.source_url,
        why_bullets: job.why_bullets,
        caution_bullets: job.caution_bullets,
      });
      setDraft(res.draft);
      setInfo(
        res.source === "llm"
          ? "AI selected relevant experience for this posting. Review and adjust before exporting."
          : "Keyword match selected items for this posting (model unavailable). Review before exporting.",
      );
    } catch (err) {
      showError(err, "Failed to tailor resume");
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.resume.updateDraft(draft.id, draft.document);
      setDraft(res);
      setInfo("Selection saved.");
    } catch (err) {
      showError(err, "Failed to save draft");
    } finally {
      setBusy(false);
    }
  }

  async function acceptAndPreview() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api.resume.updateDraft(draft.id, draft.document);
      const accepted = await api.resume.acceptDraft(saved.id);
      setDraft(accepted);
      const html = await api.resume.fetchHtml(accepted.id);
      const blobUrl = URL.createObjectURL(new Blob([html], { type: "text/html" }));
      const preview = window.open(blobUrl, "_blank", "noopener,noreferrer");
      if (!preview) {
        setInfo("Resume accepted. Popup blocked — allow popups, then try again to preview.");
      } else {
        setInfo("Resume accepted. Use Print / Save PDF in the preview tab.");
      }
    } catch (err) {
      showError(err, "Failed to generate resume");
    } finally {
      setBusy(false);
    }
  }

  function patchDocument(next: ResumeDocument) {
    if (!draft) return;
    setDraft({ ...draft, document: next });
  }

  const doc = draft?.document;

  const body = (
    <div className={`space-y-4 ${isPage ? "" : "border-t border-border-subtle px-4 py-4"}`}>
      <div ref={alertRef} className="space-y-3">
        {error ? <Alert tone="error">{error}</Alert> : null}
        {info ? <Alert tone="success">{info}</Alert> : null}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="button" variant="secondary" disabled={busy} onClick={() => void buildMaster()}>
          Build full resume
        </Button>
        <Button type="button" disabled={busy || !job} onClick={() => void tailorForJob()}>
          {job ? `Tailor for ${job.title}` : "Tailor for discussed job"}
        </Button>
      </div>
      {job ? (
        <p className="text-xs text-muted">
          Target: {job.title} at {job.company}
        </p>
      ) : (
        <p className="text-xs text-subtle">
          Tip: open a job on the deck and click Discuss with Advisor to set the target posting.
        </p>
      )}

      {doc ? (
        <div className="space-y-4">
          {doc.rationale ? (
            <p className="rounded-[var(--radius-button)] border border-border bg-surface-raised px-3 py-2 text-sm text-muted">
              {doc.rationale}
            </p>
          ) : null}

          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-ink-text">Experience & accomplishments</h3>
            {(doc.roles || []).map((role) => (
              <div
                key={role.experience_id || role.title}
                className="rounded-[var(--radius-button)] border border-border bg-surface-raised p-3"
              >
                <label className="flex items-start gap-2 text-sm font-medium text-ink-text">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={role.included}
                    onChange={(e) =>
                      patchDocument(toggleRole(doc, role.experience_id || "", e.target.checked))
                    }
                  />
                  <span>
                    {role.title}
                    <span className="block text-xs font-normal text-muted">
                      {role.company_name}
                      {role.meta ? ` · ${role.meta}` : ""}
                    </span>
                  </span>
                </label>
                {role.included ? (
                  <ul className="mt-2 space-y-1.5 pl-6">
                    {role.highlights.map((h, hi) => (
                      <li key={`${role.experience_id}-${hi}`}>
                        <label className="flex items-start gap-2 text-xs text-muted">
                          <input
                            type="checkbox"
                            className="mt-0.5"
                            checked={h.included}
                            onChange={(e) =>
                              patchDocument(
                                toggleHighlight(
                                  doc,
                                  role.experience_id || "",
                                  hi,
                                  e.target.checked,
                                ),
                              )
                            }
                          />
                          <span>{h.text}</span>
                        </label>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </div>

          {(doc.skill_groups || []).length > 0 ? (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-ink-text">Skills</h3>
              {(doc.skill_groups || []).map((group, gi) => (
                <div key={group.label} className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
                    {group.label}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {group.items.map((item, ii) => (
                      <label
                        key={`${group.label}-${item.text}`}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
                          item.included
                            ? "border-brand-strong/30 bg-brand/10 text-ink-text"
                            : "border-border text-subtle"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={item.included}
                          onChange={(e) =>
                            patchDocument(toggleSkill(doc, gi, ii, e.target.checked))
                          }
                        />
                        {item.text}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          <div className="flex flex-col gap-2 sm:flex-row">
            <Button type="button" variant="secondary" disabled={busy} onClick={() => void saveDraft()}>
              Save selection
            </Button>
            <Button type="button" disabled={busy} onClick={() => void acceptAndPreview()}>
              Accept & generate resume
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );

  if (isPage) {
    return <div className="pb-4">{body}</div>;
  }

  return (
    <div className="mb-4 overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-surface-raised/60"
        aria-expanded={open}
      >
        <div>
          <p className="text-sm font-semibold text-ink-text">Resume builder</p>
          <p className="text-xs text-muted">
            Build a full ATS resume or tailor one to a job discussion — then edit what is included.
          </p>
        </div>
        <span className="text-sm font-semibold text-brand-strong">{open ? "Hide" : "Open"}</span>
      </button>
      {open ? body : null}
    </div>
  );
}
