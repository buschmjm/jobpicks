import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { FieldInput } from "./ui/Field";
import type { Skill } from "../types";

type Props = {
  skills: Skill[];
  onChange: (skills: Skill[]) => void;
};

export function SkillPicker({ skills, onChange }: Props) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Skill[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  const selectedIds = useMemo(() => new Set(skills.map((s) => s.id)), [skills]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      api.skills
        .search(query)
        .then((res) => {
          setHits(res.items.filter((item) => !selectedIds.has(item.id)));
          setError(null);
        })
        .catch((err) => {
          setError(err instanceof ApiError ? err.message : "Couldn't search skills");
        });
    }, 180);
    return () => window.clearTimeout(handle);
  }, [query, selectedIds]);

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
      hit.normalized_name === normalizedQuery || hit.name.toLowerCase() === normalizedQuery,
  );
  const canCreate = normalizedQuery.length >= 2 && !exactHit;

  function add(skill: Skill) {
    if (selectedIds.has(skill.id)) return;
    onChange([...skills, skill]);
    setQuery("");
    setOpen(false);
  }

  async function create() {
    const name = query.trim();
    if (!name) return;
    try {
      const created = await api.skills.create(name);
      add(created);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create skill");
    }
  }

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface p-3">
      <label className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">Skills</label>
      <p className="mt-1 text-xs text-muted">
        Search the shared directory, or create a skill if it isn't there yet.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {skills.map((skill) => (
          <button
            key={skill.id}
            type="button"
            onClick={() => onChange(skills.filter((item) => item.id !== skill.id))}
            className="rounded-full border border-stone-200 bg-stone-50 px-3 py-1 text-sm text-ink-text hover:border-danger/30 hover:bg-danger-muted/40 hover:text-danger"
          >
            {skill.name} ×
          </button>
        ))}
        {skills.length === 0 ? (
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
          placeholder="Search or add a skill"
        />
        {open && (hits.length > 0 || canCreate) ? (
          <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-auto rounded-[var(--radius-button)] border border-border bg-surface-raised py-1 shadow-xl">
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
