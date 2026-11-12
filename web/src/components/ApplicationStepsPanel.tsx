import { useMemo, useState, type FormEvent } from "react";
import { api } from "../api/client";
import { Button } from "./ui/Button";
import { FieldGroup, FieldInput } from "./ui/Field";
import type { ApplicationStep } from "../types";

type ApplicationStepsPanelProps = {
  steps: ApplicationStep[];
  onChange: (steps: ApplicationStep[]) => void | Promise<void>;
  onSaveTemplate?: (steps: ApplicationStep[]) => void | Promise<void>;
  compact?: boolean;
  disabled?: boolean;
};

function sortSteps(steps: ApplicationStep[]): ApplicationStep[] {
  return [...steps].sort((a, b) => a.order - b.order);
}

function newStepId(): string {
  return `step-${crypto.randomUUID()}`;
}

export function ApplicationStepsPanel({
  steps,
  onChange,
  onSaveTemplate,
  compact = false,
  disabled = false,
}: ApplicationStepsPanelProps) {
  const [newLabel, setNewLabel] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [savingTemplate, setSavingTemplate] = useState(false);

  const ordered = useMemo(() => sortSteps(steps), [steps]);
  const doneCount = ordered.filter((step) => step.done).length;
  const total = ordered.length;
  const progress = total > 0 ? Math.round((doneCount / total) * 100) : 0;

  async function persist(next: ApplicationStep[]) {
    await onChange(sortSteps(next));
  }

  async function toggleStep(stepId: string) {
    const next = ordered.map((step) =>
      step.id === stepId ? { ...step, done: !step.done } : step,
    );
    await persist(next);
  }

  async function removeStep(stepId: string) {
    const next = ordered
      .filter((step) => step.id !== stepId)
      .map((step, index) => ({ ...step, order: index }));
    await persist(next);
  }

  async function addStep(event: FormEvent) {
    event.preventDefault();
    const label = newLabel.trim();
    if (!label) return;
    const next = [
      ...ordered,
      { id: newStepId(), label, done: false, order: ordered.length },
    ];
    setNewLabel("");
    await persist(next);
  }

  async function saveEdit(stepId: string) {
    const label = editLabel.trim();
    if (!label) return;
    const next = ordered.map((step) =>
      step.id === stepId ? { ...step, label } : step,
    );
    setEditingId(null);
    setEditLabel("");
    await persist(next);
  }

  async function moveStep(stepId: string, direction: -1 | 1) {
    const index = ordered.findIndex((step) => step.id === stepId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ordered.length) return;
    const next = [...ordered];
    const [moved] = next.splice(index, 1);
    next.splice(target, 0, moved);
    await persist(next.map((step, order) => ({ ...step, order })));
  }

  async function handleSaveTemplate() {
    if (!onSaveTemplate) return;
    setSavingTemplate(true);
    try {
      await onSaveTemplate(ordered);
    } finally {
      setSavingTemplate(false);
    }
  }

  return (
    <div className={compact ? "space-y-3" : "space-y-4"}>
      <div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-subtle">
            Application progress
          </p>
          <span className="text-xs font-medium text-muted">
            {doneCount}/{total} complete
          </span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-raised">
          <div
            className="h-full rounded-full bg-accent-strong transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <ul className="space-y-2">
        {ordered.map((step, index) => (
          <li
            key={step.id}
            className="rounded-[var(--radius-button)] border border-border bg-surface px-3 py-2"
          >
            <div className="flex items-start gap-3">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-accent-strong"
                checked={step.done}
                disabled={disabled}
                onChange={() => void toggleStep(step.id)}
                aria-label={`Mark ${step.label} complete`}
              />
              <div className="min-w-0 flex-1">
                {editingId === step.id ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <FieldInput
                      value={editLabel}
                      onChange={(event) => setEditLabel(event.target.value)}
                      autoFocus
                    />
                    <Button size="sm" onClick={() => void saveEdit(step.id)}>
                      Save
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditingId(null);
                        setEditLabel("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <p
                    className={`text-sm ${step.done ? "text-muted line-through" : "text-ink-text"}`}
                  >
                    {step.label}
                  </p>
                )}
              </div>
              {!disabled && editingId !== step.id ? (
                <div className="flex shrink-0 gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label="Move step up"
                    disabled={index === 0}
                    onClick={() => void moveStep(step.id, -1)}
                  >
                    ↑
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label="Move step down"
                    disabled={index === ordered.length - 1}
                    onClick={() => void moveStep(step.id, 1)}
                  >
                    ↓
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setEditingId(step.id);
                      setEditLabel(step.label);
                    }}
                  >
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void removeStep(step.id)}
                  >
                    Remove
                  </Button>
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ul>

      {!disabled ? (
        <form onSubmit={(event) => void addStep(event)} className="flex flex-wrap items-end gap-2">
          <div className="min-w-[12rem] flex-1">
            <FieldGroup label="Add a step">
              <FieldInput
                value={newLabel}
                onChange={(event) => setNewLabel(event.target.value)}
                placeholder="e.g. Request referral"
              />
            </FieldGroup>
          </div>
          <Button type="submit" size="sm" variant="secondary" disabled={!newLabel.trim()}>
            Add step
          </Button>
        </form>
      ) : null}

      {!disabled && onSaveTemplate ? (
        <Button
          size="sm"
          variant="ghost"
          disabled={savingTemplate || ordered.length === 0}
          onClick={() => void handleSaveTemplate()}
        >
          {savingTemplate ? "Saving default…" : "Save as my default steps"}
        </Button>
      ) : null}
    </div>
  );
}

export async function saveApplicationStepTemplate(steps: ApplicationStep[]) {
  await api.todo.saveStepTemplate(steps);
}
