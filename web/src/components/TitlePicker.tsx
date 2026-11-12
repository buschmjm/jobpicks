import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { FieldInput } from "./ui/Field";
import type { JobTitle } from "../types";

type Props = {
  titles: JobTitle[];
  onChange: (titles: JobTitle[]) => void;
  label?: string;
};

export function TitlePicker({ titles, onChange, label = "Target roles" }: Props) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<JobTitle[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  const selectedIds = useMemo(() => new Set(titles.map((t) => t.id)), [titles]);
  const selectedNames = useMemo(
    () => new Set(titles.map((t) => t.normalized_name)),
    [titles],
  );

  useEffect(() => {
    const handle = window.setTimeout(() => {
      api.titles
        .search(query)
        .then((res) => {
          setHits(
            res.items.filter(
              (item) =>
                !selectedIds.has(item.id) && !selectedNames.has(item.normalized_name),
            ),
          );
          setError(null);
        })
        .catch((err) => {
          setError(err instanceof ApiError ? err.message : "Couldn't search titles");
        });
    }, query.trim() ? 180 : 0);
    return () => window.clearTimeout(handle);
  }, [query, selectedIds, selectedNames]);

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (!boxRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const normalizedQuery = query.trim().toLowerCase();
  const exactHit = hits.some(
    (hit) =>
      hit.normalized_name === normalizedQuery.replace(/[^\w\s]/g, "").replace(/\s+/g, " ") ||
      hit.name.toLowerCase() === normalizedQuery,
  );
  const canCreate = normalizedQuery.length >= 2 && !exactHit && titles.length < 20;

  function add(title: JobTitle) {
    if (selectedIds.has(title.id) || selectedNames.has(title.normalized_name)) return;
    if (titles.length >= 20) return;
    onChange([...titles, title]);
    setQuery("");
    setOpen(false);
  }

  async function create() {
    const name = query.trim();
    if (!name) return;
    try {
      const created = await api.titles.create(name);
      add(created);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create title");
    }
  }

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface p-3">
      <label className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
        {label}
      </label>
      <p className="mt-1 text-xs text-muted">
        Type to autofill from titles already in the job corpus and shared catalog. Create a new one
        only if it is missing.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {titles.map((title) => (
          <button
            key={title.id}
            type="button"
            onClick={() => onChange(titles.filter((item) => item.id !== title.id))}
            className="rounded-full border border-stone-200 bg-stone-50 px-3 py-1 text-sm text-ink-text hover:border-danger/30 hover:bg-danger-muted/40 hover:text-danger"
          >
            {title.name} ×
          </button>
        ))}
        {titles.length === 0 ? (
          <span className="text-sm text-subtle">None selected yet</span>
        ) : null}
      </div>
      <div ref={boxRef} className="relative mt-2">
        <FieldInput
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              if (hits[0]) add(hits[0]);
              else if (canCreate) void create();
            }
          }}
          placeholder="Type a role — e.g. nurse, engineer, manager"
        />
        {open && (hits.length > 0 || canCreate) ? (
          <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-[var(--radius-button)] border border-border bg-surface-raised py-1 shadow-xl">
            {!query.trim() && hits.length > 0 ? (
              <li className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-subtle">
                Popular titles
              </li>
            ) : null}
            {hits.map((hit) => (
              <li key={hit.id}>
                <button
                  type="button"
                  onClick={() => add(hit)}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm text-ink-text hover:bg-surface-overlay"
                >
                  <span>{hit.name}</span>
                  {hit.use_count > 0 ? (
                    <span className="text-xs text-subtle">{hit.use_count}</span>
                  ) : null}
                </button>
              </li>
            ))}
            {canCreate ? (
              <li>
                <button
                  type="button"
                  onClick={() => void create()}
                  className="w-full px-3 py-2 text-left text-sm text-brand-strong hover:bg-surface-overlay"
                >
                  Create “{query.trim()}”
                </button>
              </li>
            ) : null}
          </ul>
        ) : null}
      </div>
      {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
    </div>
  );
}
