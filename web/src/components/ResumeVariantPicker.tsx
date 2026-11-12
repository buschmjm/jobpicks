import { FormEvent, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, ApiError } from "../api/client";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";
import { FieldGroup, FieldInput, FieldSelect } from "./ui/Field";
import { InlineSpinner } from "./ui/NavIcon";
import type { ResumeVariant } from "../types";

function slugFromLabel(label: string): string {
  return label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

type Props = {
  selectedId: string | null;
  onChange: (variant: ResumeVariant | null) => void;
};

export function ResumeVariantPicker({ selectedId, onChange }: Props) {
  const [variants, setVariants] = useState<ResumeVariant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [label, setLabel] = useState("");
  const [emphasisNotes, setEmphasisNotes] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.resume.variants.list();
        if (cancelled) return;
        setVariants(res.variants);
        const selected =
          res.variants.find((v) => v.id === selectedId) ??
          res.variants.find((v) => v.is_default) ??
          res.variants[0] ??
          null;
        if (selected && selected.id !== selectedId) {
          onChange(selected);
        } else if (!selected) {
          onChange(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load resume variants");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Load variants once on mount; parent owns selectedId after initial pick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function closeModal() {
    if (creating) return;
    setModalOpen(false);
    setLabel("");
    setEmphasisNotes("");
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    const trimmed = label.trim();
    if (!trimmed || creating) return;
    setCreating(true);
    setError(null);
    try {
      const variant = await api.resume.variants.create({
        slug: slugFromLabel(trimmed),
        label: trimmed,
        emphasis_notes: emphasisNotes.trim() || null,
      });
      setVariants((prev) => [...prev, variant]);
      onChange(variant);
      closeModal();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create variant");
    } finally {
      setCreating(false);
    }
  }

  async function handleSelect(nextId: string) {
    const next = variants.find((v) => v.id === nextId) ?? null;
    if (!next) return;
    onChange(next);
    if (!next.is_default) {
      try {
        const updated = await api.resume.variants.setDefault(next.id);
        setVariants((prev) =>
          prev.map((v) => ({
            ...v,
            is_default: v.id === updated.id,
          })),
        );
        onChange(updated);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to set default variant");
      }
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[12rem] flex-1">
          <FieldGroup label="Resume variant">
            {loading ? (
              <div className="mt-1.5 flex items-center gap-2 text-sm text-muted">
                <InlineSpinner label="Loading variants" />
                Loading…
              </div>
            ) : (
              <FieldSelect
                value={selectedId ?? ""}
                disabled={!variants.length}
                onChange={(e) => void handleSelect(e.target.value)}
              >
                {!variants.length ? <option value="">No variants yet</option> : null}
                {variants.map((variant) => (
                  <option key={variant.id} value={variant.id}>
                    {variant.label}
                    {variant.is_default ? " (default)" : ""}
                  </option>
                ))}
              </FieldSelect>
            )}
          </FieldGroup>
        </div>
        <Button type="button" variant="secondary" size="sm" disabled={loading} onClick={() => setModalOpen(true)}>
          New variant
        </Button>
      </div>

      {error && !modalOpen ? <Alert tone="error" className="mt-2">{error}</Alert> : null}

      {modalOpen
        ? createPortal(
            <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true">
              <button
                type="button"
                className="absolute inset-0 bg-ink-text/40 backdrop-blur-[2px]"
                aria-label="Close"
                onClick={closeModal}
              />
              <form
                onSubmit={(e) => void handleCreate(e)}
                className="relative mx-auto w-full max-w-md rounded-t-[var(--radius-card)] border border-border bg-surface p-4 shadow-lg sm:rounded-[var(--radius-card)]"
              >
                <h2 className="font-display text-lg text-ink-text">Create resume variant</h2>
                <p className="mt-1 text-sm text-muted">
                  Save a separate resume version — useful for different target roles.
                </p>
                {error ? <Alert tone="error" className="mt-3">{error}</Alert> : null}
                <div className="mt-4 space-y-3">
                  <FieldGroup label="Label">
                    <FieldInput
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                      placeholder="e.g. Senior backend"
                      autoFocus
                      disabled={creating}
                    />
                  </FieldGroup>
                  <FieldGroup label="Emphasis notes (optional)">
                    <FieldInput
                      value={emphasisNotes}
                      onChange={(e) => setEmphasisNotes(e.target.value)}
                      placeholder="Who this version is for"
                      disabled={creating}
                    />
                  </FieldGroup>
                </div>
                <div className="mt-4 flex gap-2">
                  <Button type="submit" disabled={creating || !label.trim()}>
                    {creating ? "Creating…" : "Create"}
                  </Button>
                  <Button type="button" variant="secondary" disabled={creating} onClick={closeModal}>
                    Cancel
                  </Button>
                </div>
              </form>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
