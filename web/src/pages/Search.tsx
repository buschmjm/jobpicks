import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import { Button } from "../components/ui/Button";
import { Alert, EmptyState } from "../components/ui/Alert";
import { FieldGroup, FieldInput, FieldSelect } from "../components/ui/Field";
import { PageHeader } from "../components/ui/PageHeader";
import type {
  JobSearchFacetOption,
  JobSearchFacets,
  JobSearchHit,
  JobSearchParams,
  JobSearchSort,
} from "../types";

const SORT_OPTIONS: { value: JobSearchSort; label: string }[] = [
  { value: "relevance", label: "Best match" },
  { value: "match", label: "Profile fit" },
  { value: "date", label: "Newest" },
  { value: "salary", label: "Salary" },
  { value: "attainability", label: "Attainability" },
];

const POSTED_OPTIONS = [
  { value: "", label: "Any time" },
  { value: "1", label: "Last 24 hours" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

const EMPTY_FACETS: JobSearchFacets = {
  remote_modes: [],
  industries: [],
  countries: [],
  states: [],
  sources: [],
  employment_types: [],
  seniority_levels: [],
};

function hitBadge(hit: JobSearchHit): { label: string; className: string } | null {
  if (hit.stretch) {
    return {
      label: "Stretch",
      className: "border-amber-200 bg-amber-50 text-accent-strong",
    };
  }
  if (hit.reach) {
    return {
      label: "Reach",
      className: "border-indigo-200 bg-indigo-50 text-explore",
    };
  }
  return null;
}

function workModeLabel(mode: string): string {
  if (mode === "remote") return "Remote";
  if (mode === "hybrid") return "Hybrid";
  if (mode === "onsite") return "On-site";
  return "Unknown";
}

function toggleValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function toggleNumber(values: number[], value: number): number[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function FilterChipGroup({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: JobSearchFacetOption[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  if (!options.length) return null;
  return (
    <FieldGroup label={label}>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const active = selected.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onToggle(option.value)}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                active
                  ? "border-brand-strong bg-brand-muted text-brand-strong"
                  : "border-border bg-surface text-muted hover:border-muted hover:text-ink-text"
              }`}
            >
              {option.label}
              <span className="ml-1 text-[10px] opacity-70">({option.count})</span>
            </button>
          );
        })}
      </div>
    </FieldGroup>
  );
}

function SeniorityFilter({
  options,
  selected,
  onToggle,
}: {
  options: JobSearchFacetOption[];
  selected: number[];
  onToggle: (value: number) => void;
}) {
  if (!options.length) return null;
  return (
    <FieldGroup label="Seniority">
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const value = Number(option.value);
          const active = selected.includes(value);
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onToggle(value)}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium capitalize transition ${
                active
                  ? "border-brand-strong bg-brand-muted text-brand-strong"
                  : "border-border bg-surface text-muted hover:border-muted hover:text-ink-text"
              }`}
            >
              {option.label}
              <span className="ml-1 text-[10px] opacity-70">({option.count})</span>
            </button>
          );
        })}
      </div>
    </FieldGroup>
  );
}

export function SearchPage() {
  const [draftQuery, setDraftQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [company, setCompany] = useState("");
  const [sort, setSort] = useState<JobSearchSort>("relevance");
  const [minSalary, setMinSalary] = useState("");
  const [postedWithinDays, setPostedWithinDays] = useState("");
  const [directOnly, setDirectOnly] = useState(false);
  const [includeReach, setIncludeReach] = useState(true);
  const [includeStretch, setIncludeStretch] = useState(true);
  const [remoteModes, setRemoteModes] = useState<string[]>([]);
  const [seniority, setSeniority] = useState<number[]>([]);
  const [industries, setIndustries] = useState<string[]>([]);
  const [countries, setCountries] = useState<string[]>([]);
  const [states, setStates] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [employmentTypes, setEmploymentTypes] = useState<string[]>([]);
  const [facets, setFacets] = useState<JobSearchFacets>(EMPTY_FACETS);
  const [results, setResults] = useState<JobSearchHit[]>([]);
  const [profileComplete, setProfileComplete] = useState(true);
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [facetsLoading, setFacetsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(true);

  const searchParams = useMemo<JobSearchParams>(
    () => ({
      q: appliedQuery,
      sort,
      company: company.trim() || undefined,
      min_salary: minSalary ? Number(minSalary) : undefined,
      posted_within_days: postedWithinDays ? Number(postedWithinDays) : undefined,
      direct_only: directOnly,
      include_reach: includeReach,
      include_stretch: includeStretch,
      remote_mode: remoteModes,
      seniority,
      industry: industries,
      country: countries,
      state: states,
      source: sources,
      employment_type: employmentTypes,
    }),
    [
      appliedQuery,
      sort,
      company,
      minSalary,
      postedWithinDays,
      directOnly,
      includeReach,
      includeStretch,
      remoteModes,
      seniority,
      industries,
      countries,
      states,
      sources,
      employmentTypes,
    ],
  );

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (company.trim()) count += 1;
    if (minSalary) count += 1;
    if (postedWithinDays) count += 1;
    if (directOnly) count += 1;
    if (!includeReach) count += 1;
    if (!includeStretch) count += 1;
    count +=
      remoteModes.length +
      seniority.length +
      industries.length +
      countries.length +
      states.length +
      sources.length +
      employmentTypes.length;
    return count;
  }, [
    company,
    minSalary,
    postedWithinDays,
    directOnly,
    includeReach,
    includeStretch,
    remoteModes,
    seniority,
    industries,
    countries,
    states,
    sources,
    employmentTypes,
  ]);

  const runSearch = useCallback(async (params: JobSearchParams) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.search.jobs(params);
      setResults(res.results);
      setProfileComplete(res.profile_complete);
      setSubmittedQuery(res.query);
      setSort(res.sort);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void api.events.track("page_view", null, { page: "search" }).catch(() => undefined);
    void api.search
      .facets()
      .then(setFacets)
      .catch(() => setFacets(EMPTY_FACETS))
      .finally(() => setFacetsLoading(false));
  }, []);

  useEffect(() => {
    void runSearch(searchParams);
  }, [runSearch, searchParams]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setAppliedQuery(draftQuery);
  }

  function clearFilters() {
    setCompany("");
    setMinSalary("");
    setPostedWithinDays("");
    setDirectOnly(false);
    setIncludeReach(true);
    setIncludeStretch(true);
    setRemoteModes([]);
    setSeniority([]);
    setIndustries([]);
    setCountries([]);
    setStates([]);
    setSources([]);
    setEmploymentTypes([]);
  }

  return (
    <div className="pb-4">
      <PageHeader
        title="Search jobs"
        subtitle="Browse the full corpus with filters. Results are ranked for your profile when onboarding is complete."
      />

      {error ? <Alert tone="error" className="mb-4">{error}</Alert> : null}
      {!profileComplete ? (
        <Alert tone="warning" className="mb-4">
          Finish onboarding for personalized match scores. Text relevance and filters still work.
        </Alert>
      ) : null}

      <form onSubmit={handleSubmit} className="mb-4 space-y-4">
        <div className="grid gap-3 lg:grid-cols-[1fr_auto_auto] lg:items-end">
          <FieldGroup label="Keywords">
            <FieldInput
              value={draftQuery}
              onChange={(e) => setDraftQuery(e.target.value)}
              placeholder="Title, skills, keywords…"
            />
          </FieldGroup>
          <FieldGroup label="Sort by">
            <FieldSelect value={sort} onChange={(e) => setSort(e.target.value as JobSearchSort)}>
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </FieldSelect>
          </FieldGroup>
          <Button type="submit" size="lg" disabled={loading}>
            {loading ? "Searching…" : "Search"}
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setFiltersOpen((open) => !open)}
          >
            {filtersOpen ? "Hide filters" : "Show filters"}
            {activeFilterCount ? ` (${activeFilterCount})` : ""}
          </Button>
          {activeFilterCount ? (
            <Button type="button" variant="ghost" size="sm" onClick={clearFilters}>
              Clear filters
            </Button>
          ) : null}
        </div>

        {filtersOpen ? (
          <div className="rounded-[var(--radius-card)] border border-border bg-surface p-4 shadow-sm">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <FieldGroup label="Company">
                <FieldInput
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="Company name"
                />
              </FieldGroup>
              <FieldGroup label="Minimum salary (USD)">
                <FieldInput
                  inputMode="numeric"
                  value={minSalary}
                  onChange={(e) => setMinSalary(e.target.value.replace(/[^\d]/g, ""))}
                  placeholder="e.g. 120000"
                />
              </FieldGroup>
              <FieldGroup label="Posted">
                <FieldSelect
                  value={postedWithinDays}
                  onChange={(e) => setPostedWithinDays(e.target.value)}
                >
                  {POSTED_OPTIONS.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </FieldSelect>
              </FieldGroup>
            </div>

            <div className="mt-4 grid gap-4">
              <FilterChipGroup
                label="Work mode"
                options={facets.remote_modes}
                selected={remoteModes}
                onToggle={(value) => setRemoteModes((prev) => toggleValue(prev, value))}
              />
              <SeniorityFilter
                options={facets.seniority_levels}
                selected={seniority}
                onToggle={(value) => setSeniority((prev) => toggleNumber(prev, value))}
              />
              <FilterChipGroup
                label="Industry"
                options={facets.industries}
                selected={industries}
                onToggle={(value) => setIndustries((prev) => toggleValue(prev, value))}
              />
              <FilterChipGroup
                label="Country"
                options={facets.countries}
                selected={countries}
                onToggle={(value) => setCountries((prev) => toggleValue(prev, value))}
              />
              <FilterChipGroup
                label="State / region"
                options={facets.states}
                selected={states}
                onToggle={(value) => setStates((prev) => toggleValue(prev, value))}
              />
              <FilterChipGroup
                label="Source"
                options={facets.sources}
                selected={sources}
                onToggle={(value) => setSources((prev) => toggleValue(prev, value))}
              />
              <FilterChipGroup
                label="Employment type"
                options={facets.employment_types}
                selected={employmentTypes}
                onToggle={(value) => setEmploymentTypes((prev) => toggleValue(prev, value))}
              />
            </div>

            <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted">
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={directOnly}
                  onChange={(e) => setDirectOnly(e.target.checked)}
                />
                Direct listings only
              </label>
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeReach}
                  onChange={(e) => setIncludeReach(e.target.checked)}
                />
                Include reach roles
              </label>
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeStretch}
                  onChange={(e) => setIncludeStretch(e.target.checked)}
                />
                Include stretch roles
              </label>
            </div>

            {facetsLoading ? (
              <p className="mt-3 text-xs text-subtle">Loading filter options…</p>
            ) : null}
          </div>
        ) : null}
      </form>

      {loading && results.length === 0 ? (
        <p className="text-sm text-muted">Searching…</p>
      ) : results.length === 0 ? (
        <EmptyState
          title={submittedQuery || activeFilterCount ? "No matches" : "No open jobs"}
          description={
            submittedQuery || activeFilterCount
              ? "Nothing matched your search and filters. Try broader keywords or fewer filters."
              : "There are no searchable jobs in the corpus right now."
          }
        />
      ) : (
        <ul className="space-y-3">
          {results.map((hit) => {
            const badge = hitBadge(hit);
            return (
              <li
                key={hit.job_id}
                className="rounded-[var(--radius-card)] border border-border bg-surface p-4 shadow-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-lg font-semibold text-ink-text">{hit.title}</h2>
                    <p className="mt-0.5 text-sm font-medium text-muted">{hit.company}</p>
                    <p className="mt-1 text-xs text-subtle">
                      {[hit.location_display, workModeLabel(hit.remote_mode), hit.salary_display]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <span className="shrink-0 rounded-xl border border-accent/30 bg-accent-muted px-2.5 py-1 text-sm font-bold tabular-nums text-accent-strong">
                    {Math.round(hit.match_score)}%
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  {badge ? (
                    <span
                      className={`inline-flex rounded-lg border px-2 py-0.5 font-semibold uppercase tracking-[0.06em] ${badge.className}`}
                    >
                      {badge.label}
                    </span>
                  ) : null}
                  {hit.industry ? (
                    <span className="rounded-lg border border-border bg-surface-raised px-2 py-0.5 text-muted">
                      {hit.industry}
                    </span>
                  ) : null}
                  {hit.source ? (
                    <span className="rounded-lg border border-border bg-surface-raised px-2 py-0.5 text-muted">
                      via {hit.source}
                    </span>
                  ) : null}
                  <span className="rounded-lg border border-border bg-surface-raised px-2 py-0.5 text-muted">
                    Attainability {Math.round(hit.attainability * 100)}%
                  </span>
                  <span className="rounded-lg border border-border bg-surface-raised px-2 py-0.5 text-muted">
                    Relevance {Math.round(hit.text_relevance * 100)}%
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
