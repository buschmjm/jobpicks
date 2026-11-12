import { Link } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { EducationEditor } from "./EducationEditor";
import { ExperienceEditor } from "./ExperienceEditor";
import {
  emptyIdentity,
  formatPhoneInput,
  ProfileIdentityEditor,
  validateIdentity,
} from "./ProfileIdentityEditor";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";
import type { Education, Experience, ProfileIdentity } from "../types";

export function ResumePanel({ variant = "collapsible" }: { variant?: "collapsible" | "page" }) {
  const isPage = variant === "page";
  const [open, setOpen] = useState(isPage);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [identityErrors, setIdentityErrors] = useState<string[]>([]);
  const [identity, setIdentity] = useState<ProfileIdentity>(emptyIdentity);
  const [experiences, setExperiences] = useState<Experience[]>([]);
  const [education, setEducation] = useState<Education[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  function applyIdentity(next: ProfileIdentity | undefined) {
    const base = next ?? emptyIdentity();
    setIdentity({
      ...emptyIdentity(),
      ...base,
      phone: formatPhoneInput(base.phone || ""),
      show_pronouns: base.show_pronouns !== false,
      links: base.links ?? [],
    });
  }

  useEffect(() => {
    if ((!open && !isPage) || loaded || loading) return;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.profile.getResume();
        applyIdentity(res.identity);
        setExperiences(res.experiences ?? []);
        setEducation(res.education ?? []);
        setLoaded(true);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load profile");
      } finally {
        setLoading(false);
      }
    })();
  }, [open, isPage, loaded, loading]);

  async function handleSave() {
    if (saving) return;
    const problems = validateIdentity(identity);
    setIdentityErrors(problems);
    if (problems.length) {
      setError("Fix the contact details below, then save again.");
      return;
    }
    setSaving(true);
    setError(null);
    setSavedMsg(null);
    try {
      const res = await api.profile.updateResume({
        identity: {
          preferred_name: identity.preferred_name,
          email: identity.email,
          phone: identity.phone,
          pronouns: identity.pronouns,
          show_pronouns: identity.show_pronouns,
          links: identity.links
            .map((link) => ({ title: link.title.trim(), url: link.url.trim() }))
            .filter((link) => link.title || link.url),
        },
        experiences: experiences.map((exp) => ({
          title: exp.title,
          company_name: exp.company_name,
          location: exp.location,
          start_date: exp.start_date,
          end_date: exp.end_date,
          is_current: exp.is_current,
          highlights: exp.highlights,
        })),
        education: education.map((row) => ({
          institution: row.institution,
          degree: row.degree,
          field: row.field,
          end_date: row.end_date,
        })),
      });
      applyIdentity(res.identity);
      setExperiences(res.experiences ?? []);
      setEducation(res.education ?? []);
      setIdentityErrors([]);
      setSavedMsg("Profile saved — resumes and advisor replies will use these details.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save profile");
    } finally {
      setSaving(false);
    }
  }

  async function handleUpload(file: File | undefined) {
    if (!file || uploading) return;
    setUploading(true);
    setError(null);
    setSavedMsg(null);
    try {
      const res = await api.profile.uploadResume(file);
      if (res.identity) applyIdentity(res.identity);
      setExperiences(res.experiences ?? []);
      setEducation(res.education ?? []);
      setLoaded(true);
      setSavedMsg(
        res.message ||
          "Resume imported. Contact details were filled from the file when missing — review and save.",
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to import resume");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const body = (
    <div className={`space-y-4 ${isPage ? "" : "border-t border-border-subtle px-4 py-4"}`}>
      {isPage ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-button)] border border-border bg-surface-raised/50 px-3 py-3">
          <div>
            <p className="text-sm font-semibold text-ink-text">Conversational resume builder</p>
            <p className="mt-0.5 text-xs text-muted">
              Chat with AI to refine your resume with a live preview.
            </p>
          </div>
          <Link
            to="/advisor/build"
            className="inline-flex items-center justify-center rounded-[var(--radius-button)] border border-brand-deep/10 bg-brand-strong px-4 py-2.5 text-sm font-semibold text-on-brand shadow-[0_2px_8px_-2px_rgba(28,25,23,0.35)] transition hover:bg-brand-deep"
          >
            Build with AI
          </Link>
        </div>
      ) : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      {savedMsg ? <Alert tone="success">{savedMsg}</Alert> : null}

      <div className="rounded-[var(--radius-button)] border border-dashed border-border bg-surface-raised/50 px-3 py-3">
        <p className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
          Re-upload resume
        </p>
        <p className="mt-1 text-xs text-muted">
          PDF or DOCX. Replaces saved work experience and education with a fresh parse.
          Empty contact fields (name, email, phone, pronouns, links) are filled from the file.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="block w-full max-w-sm text-xs text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-brand-strong file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-on-brand"
            disabled={uploading || saving}
            onChange={(e) => void handleUpload(e.target.files?.[0])}
          />
          {uploading ? <span className="text-xs text-muted">Importing…</span> : null}
        </div>
      </div>

      {loading ? <p className="text-sm text-muted">Loading profile…</p> : null}
      {!loading ? (
        <>
          <ProfileIdentityEditor
            identity={identity}
            onChange={(next) => {
              setIdentity(next);
              setIdentityErrors([]);
            }}
            errors={identityErrors}
          />

          <section className="space-y-3">
            <div>
              <h2 className="text-base font-semibold text-ink-text">Experience</h2>
              <p className="mt-1 text-xs text-muted">
                Roles and accomplishments the advisor and resume builder can pull from.
              </p>
            </div>
            <ExperienceEditor
              experiences={experiences}
              onChange={setExperiences}
              heading="Roles"
            />
          </section>

          <EducationEditor education={education} onChange={setEducation} />

          <Button type="button" fullWidth disabled={saving || uploading} onClick={() => void handleSave()}>
            {saving ? "Saving…" : "Save profile"}
          </Button>
        </>
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
          <p className="text-sm font-semibold text-ink-text">Profile</p>
          <p className="text-xs text-muted">
            Contact details, roles, accomplishments, and education — or re-upload a PDF/DOCX.
          </p>
        </div>
        <span className="text-sm font-semibold text-brand-strong">{open ? "Hide" : "Edit"}</span>
      </button>
      {open ? body : null}
    </div>
  );
}
