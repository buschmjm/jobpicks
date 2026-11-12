import { useEffect, useRef, useState } from "react";
import { FieldGroup, FieldInput, FieldTextarea } from "./ui/Field";
import type { Experience } from "../types";

type Props = {
  experiences: Experience[];
  onChange: (experiences: Experience[]) => void;
  heading?: string;
};

function emptyExperience(): Experience {
  return {
    title: "",
    company_name: "",
    location: "",
    start_date: "",
    end_date: "",
    is_current: false,
    highlights: [],
  };
}

function roleKey(exp: Experience, index: number): string {
  return exp.id ?? `role-${index}`;
}

function roleSummary(exp: Experience, index: number): string {
  const title = exp.title.trim() || `Role ${index + 1}`;
  const company = exp.company_name.trim();
  return company ? `${title} · ${company}` : title;
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={`shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
    >
      <path
        d="M6 9l6 6 6-6"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AccomplishmentTextarea({
  value,
  onChange,
  readOnly,
  placeholder,
  "aria-label": ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
  placeholder?: string;
  "aria-label"?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.max(el.scrollHeight, 40)}px`;
  }, [value]);

  return (
    <FieldTextarea
      ref={ref}
      value={value}
      readOnly={readOnly}
      placeholder={placeholder}
      aria-label={ariaLabel}
      rows={1}
      onChange={(e) => onChange(e.target.value)}
      className="!mt-0 min-h-10 flex-1 resize-none overflow-hidden leading-relaxed"
    />
  );
}

const cardClass = "overflow-hidden rounded-[var(--radius-button)] border border-border bg-surface-raised";
const linkClass = "text-xs font-semibold text-brand-strong hover:text-brand-deep";
const removeClass = "text-xs font-semibold text-danger hover:text-red-700";

export function ExperienceEditor({ experiences, onChange, heading = "Work experience" }: Props) {
  const [openKeys, setOpenKeys] = useState<Set<string>>(() => new Set());
  const [editingKeys, setEditingKeys] = useState<Set<string>>(() => new Set());

  function isOpen(key: string): boolean {
    return openKeys.has(key);
  }

  function isEditing(key: string): boolean {
    return editingKeys.has(key);
  }

  function toggle(key: string) {
    setOpenKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
        setEditingKeys((editPrev) => {
          const editNext = new Set(editPrev);
          editNext.delete(key);
          return editNext;
        });
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function startEditing(key: string) {
    setEditingKeys((prev) => new Set(prev).add(key));
  }

  function stopEditing(key: string) {
    setEditingKeys((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
  }

  function update(index: number, patch: Partial<Experience>) {
    const next = experiences.map((row, idx) => (idx === index ? { ...row, ...patch } : row));
    onChange(next);
  }

  function updateHighlight(expIndex: number, highlightIndex: number, value: string) {
    const highlights = [...experiences[expIndex].highlights];
    highlights[highlightIndex] = value;
    update(expIndex, { highlights });
  }

  function addHighlight(expIndex: number) {
    update(expIndex, { highlights: [...experiences[expIndex].highlights, ""] });
  }

  function removeHighlight(expIndex: number, highlightIndex: number) {
    const highlights = experiences[expIndex].highlights.filter((_, idx) => idx !== highlightIndex);
    update(expIndex, { highlights });
  }

  function addRole() {
    const nextIndex = experiences.length;
    const key = roleKey(emptyExperience(), nextIndex);
    onChange([...experiences, emptyExperience()]);
    setOpenKeys((prev) => new Set(prev).add(key));
    setEditingKeys((prev) => new Set(prev).add(key));
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink-text">{heading}</h3>
        <button type="button" onClick={addRole} className={linkClass}>
          + Add role
        </button>
      </div>
      {experiences.length === 0 ? (
        <p className="text-xs text-subtle">No roles yet — add one to ground the advisor.</p>
      ) : null}
      {experiences.map((exp, index) => {
        const key = roleKey(exp, index);
        const expanded = isOpen(key);
        const editing = isEditing(key);
        return (
          <div key={key} className={cardClass}>
            <button
              type="button"
              onClick={() => toggle(key)}
              className="flex w-full items-center justify-between gap-3 px-3 py-3 text-left transition hover:bg-surface/80"
              aria-expanded={expanded}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink-text">{roleSummary(exp, index)}</p>
                <p className="mt-0.5 truncate text-xs text-subtle">
                  {[
                    [exp.start_date, exp.is_current ? "present" : exp.end_date]
                      .filter(Boolean)
                      .join(" – "),
                    `${exp.highlights.length} bullet${exp.highlights.length === 1 ? "" : "s"}`,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <ChevronIcon open={expanded} />
            </button>

            {expanded ? (
              <div className="space-y-2 border-t border-border-subtle px-3 py-3">
                <FieldGroup label="Job title">
                  <FieldInput
                    value={exp.title}
                    onChange={(e) => update(index, { title: e.target.value })}
                    placeholder="e.g. Infrastructure Engineer"
                    className="!mt-0"
                    readOnly={!editing}
                  />
                </FieldGroup>
                <FieldGroup label="Company">
                  <FieldInput
                    value={exp.company_name}
                    onChange={(e) => update(index, { company_name: e.target.value })}
                    placeholder="Company name"
                    className="!mt-0"
                    readOnly={!editing}
                  />
                </FieldGroup>
                <FieldGroup label="Location">
                  <FieldInput
                    value={exp.location}
                    onChange={(e) => update(index, { location: e.target.value })}
                    placeholder="City, State or Remote"
                    className="!mt-0"
                    readOnly={!editing}
                  />
                </FieldGroup>
                <div className="grid grid-cols-2 gap-2">
                  <FieldGroup label="Start date">
                    <FieldInput
                      value={exp.start_date}
                      onChange={(e) => update(index, { start_date: e.target.value })}
                      placeholder="YYYY-MM"
                      className="!mt-0"
                      readOnly={!editing}
                    />
                  </FieldGroup>
                  <FieldGroup label="End date">
                    <FieldInput
                      value={exp.is_current ? "present" : exp.end_date}
                      onChange={(e) => {
                        const value = e.target.value;
                        if (value.toLowerCase() === "present") {
                          update(index, { is_current: true, end_date: "present" });
                        } else {
                          update(index, { is_current: false, end_date: value });
                        }
                      }}
                      placeholder="YYYY-MM or present"
                      className="!mt-0"
                      readOnly={!editing}
                    />
                  </FieldGroup>
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
                      Accomplishments
                    </p>
                    {editing ? (
                      <button type="button" onClick={() => addHighlight(index)} className={linkClass}>
                        + Add accomplishment
                      </button>
                    ) : null}
                  </div>
                  {exp.highlights.length === 0 ? (
                    <p className="text-xs text-subtle">
                      {editing
                        ? "Bullet points of what you delivered in this role."
                        : "No accomplishments listed."}
                    </p>
                  ) : null}
                  {exp.highlights.map((highlight, hi) => (
                    <div key={hi} className="flex items-start gap-2">
                      <span className="mt-3 shrink-0 text-sm leading-none text-muted" aria-hidden>
                        •
                      </span>
                      <AccomplishmentTextarea
                        value={highlight}
                        onChange={(value) => updateHighlight(index, hi, value)}
                        placeholder="Accomplishment or impact"
                        aria-label={`Accomplishment ${hi + 1}`}
                        readOnly={!editing}
                      />
                      {editing ? (
                        <button
                          type="button"
                          onClick={() => removeHighlight(index, hi)}
                          className={`${removeClass} mt-2.5 shrink-0`}
                          aria-label={`Remove accomplishment ${hi + 1}`}
                        >
                          ×
                        </button>
                      ) : null}
                    </div>
                  ))}
                </div>

                <div className="flex flex-wrap items-center gap-2 border-t border-border-subtle pt-3">
                  {editing ? (
                    <>
                      <button
                        type="button"
                        onClick={() => stopEditing(key)}
                        className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-ink-text transition hover:bg-surface-raised"
                      >
                        Done
                      </button>
                      <button
                        type="button"
                        onClick={() => onChange(experiences.filter((_, idx) => idx !== index))}
                        className={removeClass}
                      >
                        Remove role
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => startEditing(key)}
                      className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-brand-strong transition hover:bg-surface-raised"
                    >
                      Edit
                    </button>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
