import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { JobTitle, TitleSuggestion } from "../types";
import { Chip } from "./ui/Chip";

interface TitleSuggestionsProps {
  selected: JobTitle[];
  onAddTitle: (title: string) => void;
  goals?: string;
}

function SuggestionGroup({
  label,
  items,
  selected,
  onAddTitle,
}: {
  label: string;
  items: TitleSuggestion[];
  selected: Set<string>;
  onAddTitle: (title: string) => void;
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-wide text-subtle">{label}</p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => {
          const isSelected = selected.has(item.title.toLowerCase());
          return (
            <Chip
              key={`${item.tier}-${item.title}`}
              active={isSelected}
              title={item.reason}
              disabled={isSelected}
              onClick={() => onAddTitle(item.title)}
            >
              {item.title}
            </Chip>
          );
        })}
      </div>
    </div>
  );
}

export function TitleSuggestions({ selected, onAddTitle, goals }: TitleSuggestionsProps) {
  const [suggestions, setSuggestions] = useState<TitleSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const debouncedGoals = useDebounced(goals ?? "", 500);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const res = await api.career.titleSuggestions({
          goals: debouncedGoals.trim() || undefined,
        });
        if (!cancelled) {
          setSuggestions(res.suggestions);
        }
      } catch {
        if (!cancelled) {
          setSuggestions([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [debouncedGoals]);

  const selectedNames = useMemo(
    () => new Set(selected.map((item) => item.name.toLowerCase())),
    [selected],
  );
  const qualified = suggestions.filter((item) => item.tier === "qualified");
  const adjacent = suggestions.filter((item) => item.tier === "adjacent");

  if (loading) {
    return (
      <div className="mt-3 space-y-2" aria-busy="true" aria-label="Loading title suggestions">
        <div className="h-3 w-28 animate-pulse rounded bg-surface-raised" />
        <div className="flex flex-wrap gap-2">
          {[1, 2, 3, 4].map((key) => (
            <div key={key} className="h-8 w-24 animate-pulse rounded-full bg-surface-raised" />
          ))}
        </div>
      </div>
    );
  }

  if (suggestions.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 space-y-3 rounded-lg border border-border bg-surface-raised/50 p-3">
      <div>
        <p className="text-sm font-medium text-ink-text">Suggested for you</p>
        <p className="mt-0.5 text-xs text-subtle">Click a title to add it as a tag.</p>
      </div>
      <SuggestionGroup
        label="Qualified"
        items={qualified}
        selected={selectedNames}
        onAddTitle={onAddTitle}
      />
      <SuggestionGroup
        label="Worth exploring"
        items={adjacent}
        selected={selectedNames}
        onAddTitle={onAddTitle}
      />
    </div>
  );
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}
