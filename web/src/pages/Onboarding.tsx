import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { SkillPicker } from "../components/SkillPicker";
import { ExperienceEditor } from "../components/ExperienceEditor";
import { EducationEditor } from "../components/EducationEditor";
import {
  emptyIdentity,
  formatPhoneInput,
  ProfileIdentityEditor,
  validateIdentity,
} from "../components/ProfileIdentityEditor";
import { AddressAutocomplete } from "../components/AddressAutocomplete";
import { TitlePicker } from "../components/TitlePicker";
import { TitleSuggestions } from "../components/TitleSuggestions";
import { Button } from "../components/ui/Button";
import { Alert } from "../components/ui/Alert";
import { FieldGroup, FieldInput, FieldSelect, FieldTextarea } from "../components/ui/Field";
import { PageHeader } from "../components/ui/PageHeader";
import { SurfaceCard } from "../components/ui/Alert";
import { useAuth } from "../context/AuthContext";
import { useGoogleMapsApiKey } from "../hooks/useGoogleMapsApiKey";
import { deckHomePath, useIsDesktop } from "../hooks/useMediaQuery";
import type { Education, Experience, JobTitle, ProfileFact, ProfileIdentity, Skill } from "../types";

type Step = "resume" | "profile" | "questionnaire";

const STEPS: { key: Step; label: string }[] = [
  { key: "resume", label: "Resume" },
  { key: "profile", label: "Profile" },
  { key: "questionnaire", label: "Preferences" },
];

/** Contact fields live in the identity editor — hide duplicate fact cards. */
const IDENTITY_FACT_KEYS = new Set([
  "full_name",
  "name",
  "email",
  "phone",
  "pronouns",
]);

function identityFromUpload(
  scraped: ProfileIdentity | null | undefined,
  facts: ProfileFact[],
  accountEmail: string | undefined,
): ProfileIdentity {
  const base = { ...emptyIdentity(), ...(scraped ?? {}) };
  const fact = (key: string) => facts.find((f) => f.key === key)?.value?.trim() || "";
  return {
    preferred_name: base.preferred_name || fact("full_name") || fact("name") || "",
    email: base.email || fact("email") || accountEmail || "",
    phone: formatPhoneInput(base.phone || fact("phone") || ""),
    pronouns: base.pronouns || fact("pronouns") || "",
    show_pronouns: base.show_pronouns !== false,
    links: base.links ?? [],
  };
}

function syncIdentityIntoFacts(facts: ProfileFact[], identity: ProfileIdentity): ProfileFact[] {
  const next = [...facts];
  const upsert = (key: string, value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    const idx = next.findIndex((f) => f.key === key);
    if (idx >= 0) {
      next[idx] = { ...next[idx], value: trimmed, status: "confirmed" };
    } else {
      next.push({ key, value: trimmed, status: "confirmed" });
    }
  };
  upsert("full_name", identity.preferred_name);
  upsert("email", identity.email);
  upsert("phone", identity.phone);
  if (identity.pronouns.trim()) {
    upsert("pronouns", identity.pronouns);
  }
  return next;
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, refreshUser } = useAuth();
  const isDesktop = useIsDesktop();
  const [step, setStep] = useState<Step>("resume");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [identityErrors, setIdentityErrors] = useState<string[]>([]);
  const [facts, setFacts] = useState<ProfileFact[]>([]);
  const [identity, setIdentity] = useState<ProfileIdentity>(emptyIdentity);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [experiences, setExperiences] = useState<Experience[]>([]);
  const [education, setEducation] = useState<Education[]>([]);
  const [parseFailed, setParseFailed] = useState(false);
  const [titles, setTitles] = useState<JobTitle[]>([]);
  const [minSalary, setMinSalary] = useState("");
  const [locations, setLocations] = useState("");
  const [homeLocation, setHomeLocation] = useState("");
  const [homeLat, setHomeLat] = useState<number | null>(null);
  const [homeLon, setHomeLon] = useState<number | null>(null);
  const googleMapsApiKey = useGoogleMapsApiKey();
  const [maxCommute, setMaxCommute] = useState("45");
  const [remoteOpenness, setRemoteOpenness] = useState("open_to_remote");
  const [goals, setGoals] = useState("");
  const referralFromUrl = searchParams.get("ref")?.trim() || "";

  useEffect(() => {
    if (referralFromUrl) {
      void api.events.track("page_view", null, { page: "onboarding", referral: referralFromUrl }).catch(
        () => undefined,
      );
    }
  }, [referralFromUrl]);

  const stepIndex = STEPS.findIndex((s) => s.key === step);

  async function addSuggestedTitle(title: string) {
    try {
      const created = await api.titles.create(title);
      setTitles((prev) => {
        if (
          prev.some(
            (item) => item.id === created.id || item.normalized_name === created.normalized_name,
          )
        ) {
          return prev;
        }
        return [...prev, created];
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add title");
    }
  }

  async function handleResume(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const input = (e.target as HTMLFormElement).elements.namedItem("resume") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    setLoading(true);
    setError(null);
    try {
      const res = await api.onboarding.uploadResume(file);
      const nextFacts = res.parsed_profile.facts.filter(
        (f) =>
          f.key !== "skills" &&
          f.key !== "years_experience" &&
          f.key !== "seniority_level",
      );
      setFacts(nextFacts);
      setIdentity(
        identityFromUpload(res.parsed_profile.scraped_identity, nextFacts, user?.email),
      );
      setIdentityErrors([]);
      setSkills(res.parsed_profile.skills ?? []);
      setExperiences(res.parsed_profile.experiences ?? []);
      setEducation(res.parsed_profile.education ?? []);
      setParseFailed(Boolean(res.parsed_profile.parse_failed));
      const roleTitles = (res.parsed_profile.experiences ?? [])
        .map((exp) => exp.title.trim())
        .filter(Boolean);
      const title = roleTitles[0] ?? nextFacts.find((f) => f.key === "title")?.value;
      const location = nextFacts.find((f) => f.key === "location")?.value;
      const seedTitles = roleTitles.length > 0 ? roleTitles.slice(0, 5) : title ? [title] : [];
      if (seedTitles.length > 0) {
        const resolved = await api.titles.resolve(seedTitles);
        setTitles(resolved.items);
      }
      if (location) {
        setLocations(location);
        setHomeLocation(location);
      }
      setStep("profile");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleProfileConfirm() {
    const problems = validateIdentity(identity, { requireContact: true });
    setIdentityErrors(problems);
    if (problems.length) {
      setError("Fill in your contact details above, then continue.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const factsToSave = syncIdentityIntoFacts(facts, identity);
      await api.onboarding.confirmProfile(
        factsToSave,
        skills.map((s) => s.id),
        experiences,
        education,
        {
          preferred_name: identity.preferred_name.trim(),
          email: identity.email.trim(),
          phone: identity.phone,
          pronouns: identity.pronouns.trim(),
          show_pronouns: identity.show_pronouns,
          links: identity.links
            .map((link) => ({ title: link.title.trim(), url: link.url.trim() }))
            .filter((link) => link.title || link.url),
        },
      );
      setFacts(factsToSave);
      setStep("questionnaire");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save profile");
    } finally {
      setLoading(false);
    }
  }

  async function handleQuestionnaire(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.onboarding.submitQuestionnaire({
        target_titles: titles.map((item) => item.name),
        min_salary: minSalary ? parseInt(minSalary, 10) : null,
        home_location: homeLocation.trim() || locations.split(",")[0]?.trim() || null,
        home_lat: homeLat,
        home_lon: homeLon,
        max_commute_minutes:
          remoteOpenness === "remote_only" ? null : parseInt(maxCommute, 10) || 45,
        remote_openness: remoteOpenness,
        locations: locations.split(",").map((l) => l.trim()).filter(Boolean),
        remote_preference:
          remoteOpenness === "remote_only"
            ? "remote"
            : remoteOpenness === "local_only"
              ? "onsite"
              : "any",
        industries_to_avoid: [],
        free_text_goals: goals || null,
        referral_code: referralFromUrl || null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
      });
      await refreshUser();
      navigate(`${deckHomePath(isDesktop)}?welcome=1`, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to submit");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-lg pb-2">
      <PageHeader
        title="Build your deck"
        subtitle={
          user?.email
            ? `Welcome, ${user.email.split("@")[0]}. Three quick steps to personalized job matches.`
            : "Three quick steps to personalized job matches."
        }
      />

      <div className="mb-8 flex gap-2">
        {STEPS.map((s, i) => (
          <div key={s.key} className="flex flex-1 flex-col items-center gap-1.5">
            <div
              className={`flex h-9 w-9 items-center justify-center rounded-full text-xs font-bold ${
                i <= stepIndex ? "step-indicator-active" : "step-indicator-inactive"
              }`}
            >
              {i + 1}
            </div>
            <span
              className={`text-[10px] font-semibold uppercase tracking-[0.08em] sm:text-xs ${
                step === s.key ? "step-label-active" : "step-label-inactive"
              }`}
            >
              {s.label}
            </span>
          </div>
        ))}
      </div>

      {error ? <Alert tone="error" className="mb-4">{error}</Alert> : null}

      {step === "resume" && (
        <form onSubmit={handleResume} className="space-y-4">
          <label className="block cursor-pointer rounded-[var(--radius-card)] border border-dashed border-border bg-surface/60 p-8 text-center transition hover:border-muted hover:bg-surface">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-surface-raised text-brand-strong">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M8 4h8l2 4h3v12H5V8h3l2-4z" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" />
                <path d="M9 14h6M9 17h4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
              </svg>
            </div>
            <p className="font-semibold text-ink-text">Upload your resume</p>
            <span className="mt-1 block text-sm text-muted">PDF or DOCX, max 5MB</span>
            <input
              name="resume"
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="mt-4 block w-full text-sm text-muted file:mr-4 file:rounded-[var(--radius-button)] file:border-0 file:bg-brand-strong file:px-4 file:py-2 file:font-semibold file:text-on-brand file:hover:bg-brand-deep"
              required
            />
          </label>
          <Button type="submit" fullWidth size="lg" disabled={loading}>
            {loading ? "Reading resume…" : "Continue"}
          </Button>
          <div className="relative my-2">
            <div className="absolute inset-0 flex items-center" aria-hidden>
              <div className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-app px-3 text-xs font-medium text-subtle">or</span>
            </div>
          </div>
          <Button
            type="button"
            variant="secondary"
            fullWidth
            size="lg"
            disabled={loading}
            onClick={() => navigate("/advisor/build")}
          >
            Build with AI instead
          </Button>
          <p className="text-center text-xs text-muted">
            Skip the upload — chat through your work history step by step, then finish preferences.
          </p>
        </form>
      )}

      {step === "profile" && (
        <div className="space-y-4">
          {parseFailed ? (
            <Alert tone="warning">
              We saved the file but couldn't read selectable text from it (it may be a scanned
              image). Fill in your contact details and work history below, then continue.
            </Alert>
          ) : (
            <p className="text-sm text-muted">
              Review contact details and experience pulled from your resume — edit anything that
              looks off, then continue.
            </p>
          )}
          <Alert tone="info">
            Preferred name, email, phone, pronouns, and web links appear on generated resumes.
            Add plenty of accomplishment bullets under each role so you can pick the best ones per
            application later.
          </Alert>

          <ProfileIdentityEditor
            identity={identity}
            onChange={(next) => {
              setIdentity(next);
              setIdentityErrors([]);
            }}
            errors={identityErrors}
          />

          <div className="max-h-[50vh] space-y-3 overflow-y-auto pr-1">
            <SkillPicker skills={skills} onChange={setSkills} />
            <ExperienceEditor experiences={experiences} onChange={setExperiences} />
            <EducationEditor education={education} onChange={setEducation} />
            {facts
              .filter((fact) => !IDENTITY_FACT_KEYS.has(fact.key))
              .filter((fact) => !(fact.key === "title" && experiences.length > 0))
              .map((fact) => (
              <SurfaceCard key={fact.key} padding="sm">
                <label className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
                  {fact.key.replace(/_/g, " ")}
                </label>
                {fact.key === "summary" ? (
                  <FieldTextarea
                    value={fact.value}
                    rows={4}
                    onChange={(e) => {
                      const next = [...facts];
                      const factIdx = next.findIndex((row) => row.key === fact.key);
                      if (factIdx >= 0) next[factIdx] = { ...fact, value: e.target.value };
                      setFacts(next);
                    }}
                    className="mt-1.5"
                  />
                ) : (
                  <FieldInput
                    value={fact.value}
                    onChange={(e) => {
                      const next = [...facts];
                      const factIdx = next.findIndex((row) => row.key === fact.key);
                      if (factIdx >= 0) next[factIdx] = { ...fact, value: e.target.value };
                      setFacts(next);
                    }}
                    className="mt-1.5"
                  />
                )}
                <FieldSelect
                  value={fact.status}
                  onChange={(e) => {
                    const next = [...facts];
                    const factIdx = next.findIndex((row) => row.key === fact.key);
                    if (factIdx >= 0) {
                      next[factIdx] = { ...fact, status: e.target.value as ProfileFact["status"] };
                    }
                    setFacts(next);
                  }}
                  className="mt-2 !py-1.5 text-xs"
                >
                  <option value="confirmed">Confirmed</option>
                  <option value="inferred">Inferred</option>
                  <option value="needs_confirmation">Needs review</option>
                </FieldSelect>
              </SurfaceCard>
            ))}
          </div>
          <Button type="button" fullWidth size="lg" disabled={loading} onClick={() => void handleProfileConfirm()}>
            {loading ? "Saving…" : "Looks good — next"}
          </Button>
        </div>
      )}

      {step === "questionnaire" && (
        <form onSubmit={handleQuestionnaire} className="space-y-4">
          {referralFromUrl ? (
            <Alert tone="info">
              Referral code <span className="font-mono font-semibold">{referralFromUrl}</span> will
              be applied when you finish — you and your friend each get Pro time.
            </Alert>
          ) : null}
          <div>
            <TitlePicker titles={titles} onChange={setTitles} label="Target titles" />
            <TitleSuggestions
              selected={titles}
              onAddTitle={(title) => void addSuggestedTitle(title)}
              goals={goals}
            />
          </div>
          <FieldGroup label="Min salary (USD)">
            <FieldInput type="number" value={minSalary} onChange={(e) => setMinSalary(e.target.value)} />
          </FieldGroup>
          <FieldGroup label="Home address">
            <AddressAutocomplete
              apiKey={googleMapsApiKey}
              value={homeLocation}
              onChange={(value) => {
                setHomeLocation(value);
                setHomeLat(null);
                setHomeLon(null);
              }}
              onPlaceSelect={(place) => {
                setHomeLocation(place.address);
                setHomeLat(place.lat);
                setHomeLon(place.lon);
              }}
              placeholder="Start typing your US address…"
            />
            <p className="mt-1.5 text-xs text-subtle">
              Used to filter onsite and hybrid jobs by commute time.
              {googleMapsApiKey ? " Pick an address from the suggestions for best accuracy." : ""}
            </p>
          </FieldGroup>
          <FieldGroup label="Work location preference">
            <FieldSelect
              value={remoteOpenness}
              onChange={(e) => setRemoteOpenness(e.target.value)}
            >
              <option value="local_only">Local jobs within my commute</option>
              <option value="open_to_remote">Local commute + open to US remote jobs</option>
              <option value="remote_only">Remote jobs only (US-wide)</option>
            </FieldSelect>
          </FieldGroup>
          {remoteOpenness !== "remote_only" ? (
            <FieldGroup label="Max commute (minutes)">
              <FieldSelect value={maxCommute} onChange={(e) => setMaxCommute(e.target.value)}>
                <option value="15">15 minutes</option>
                <option value="30">30 minutes</option>
                <option value="45">45 minutes</option>
                <option value="60">60 minutes</option>
                <option value="90">90 minutes</option>
              </FieldSelect>
            </FieldGroup>
          ) : null}
          <FieldGroup label="What you actually want (optional)">
            <FieldTextarea
              value={goals}
              onChange={(e) => setGoals(e.target.value)}
              rows={3}
              placeholder="Small team, no travel, growth path…"
            />
          </FieldGroup>
          <Button type="submit" fullWidth size="lg" disabled={loading || titles.length === 0}>
            {loading ? "Building your deck…" : "Open your deck →"}
          </Button>
        </form>
      )}
    </div>
  );
}
