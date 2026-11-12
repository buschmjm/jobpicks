import { useState } from "react";
import { FieldGroup, FieldInput } from "./ui/Field";
import type { Education } from "../types";

type Props = {
  education: Education[];
  onChange: (education: Education[]) => void;
};

function emptyEducation(): Education {
  return {
    institution: "",
    degree: "",
    field: "",
    end_date: "",
  };
}

function schoolKey(row: Education, index: number): string {
  return row.id ?? `school-${index}`;
}

function schoolSummary(row: Education, index: number): string {
  const institution = row.institution.trim() || `School ${index + 1}`;
  const focus = [row.degree, row.field].map((v) => v.trim()).filter(Boolean).join(", ");
  return focus ? `${institution} · ${focus}` : institution;
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

const cardClass = "overflow-hidden rounded-[var(--radius-button)] border border-border bg-surface-raised";
const linkClass = "text-xs font-semibold text-brand-strong hover:text-brand-deep";
const removeClass = "text-xs font-semibold text-danger hover:text-red-700";

export function EducationEditor({ education, onChange }: Props) {
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

  function update(index: number, patch: Partial<Education>) {
    const next = education.map((row, idx) => (idx === index ? { ...row, ...patch } : row));
    onChange(next);
  }

  function addSchool() {
    const nextIndex = education.length;
    const key = schoolKey(emptyEducation(), nextIndex);
    onChange([...education, emptyEducation()]);
    setOpenKeys((prev) => new Set(prev).add(key));
    setEditingKeys((prev) => new Set(prev).add(key));
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink-text">Education</h3>
        <button type="button" onClick={addSchool} className={linkClass}>
          + Add school
        </button>
      </div>
      {education.length === 0 ? (
        <p className="text-xs text-subtle">No schools yet — add one if you'd like.</p>
      ) : null}
      {education.map((row, index) => {
        const key = schoolKey(row, index);
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
                <p className="truncate text-sm font-medium text-ink-text">
                  {schoolSummary(row, index)}
                </p>
                <p className="mt-0.5 truncate text-xs text-subtle">
                  {row.end_date.trim() || "Graduation not set"}
                </p>
              </div>
              <ChevronIcon open={expanded} />
            </button>

            {expanded ? (
              <div className="space-y-2 border-t border-border-subtle px-3 py-3">
                <FieldGroup label="Institution">
                  <FieldInput
                    value={row.institution}
                    onChange={(e) => update(index, { institution: e.target.value })}
                    placeholder="School or university"
                    className="!mt-0"
                    readOnly={!editing}
                  />
                </FieldGroup>
                <div className="grid grid-cols-2 gap-2">
                  <FieldGroup label="Degree">
                    <FieldInput
                      value={row.degree}
                      onChange={(e) => update(index, { degree: e.target.value })}
                      placeholder="e.g. B.S."
                      className="!mt-0"
                      readOnly={!editing}
                    />
                  </FieldGroup>
                  <FieldGroup label="Field of study">
                    <FieldInput
                      value={row.field}
                      onChange={(e) => update(index, { field: e.target.value })}
                      placeholder="Major / focus"
                      className="!mt-0"
                      readOnly={!editing}
                    />
                  </FieldGroup>
                </div>
                <FieldGroup label="Graduation">
                  <FieldInput
                    value={row.end_date}
                    onChange={(e) => update(index, { end_date: e.target.value })}
                    placeholder="Year or YYYY-MM"
                    className="!mt-0"
                    readOnly={!editing}
                  />
                </FieldGroup>

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
                        onClick={() => onChange(education.filter((_, idx) => idx !== index))}
                        className={removeClass}
                      >
                        Remove school
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
