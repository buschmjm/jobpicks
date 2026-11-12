import { useEffect, useMemo, useState } from "react";
import { FieldGroup, FieldInput, FieldSelect } from "./ui/Field";
import type { ProfileIdentity, ProfileWebLink } from "../types";

type Props = {
  identity: ProfileIdentity;
  onChange: (identity: ProfileIdentity) => void;
  errors?: string[];
};

const PRONOUN_PRESETS = ["he/him/his", "she/her/hers", "they/them/theirs"] as const;
const OTHER = "__other__";

function emptyLink(): ProfileWebLink {
  return { title: "", url: "" };
}

const linkClass =
  "text-xs font-semibold text-brand-strong hover:underline disabled:opacity-50";

const fieldClass =
  "mt-1.5 w-full rounded-[var(--radius-button)] border border-border bg-surface px-3.5 py-2.5 text-sm text-ink-text placeholder:text-subtle focus:border-brand-strong/40 focus:outline-none focus:ring-2 focus:ring-brand/15";

export function emptyIdentity(): ProfileIdentity {
  return {
    preferred_name: "",
    email: "",
    phone: "",
    pronouns: "",
    show_pronouns: true,
    links: [],
  };
}

export function formatPhoneInput(raw: string): string {
  let digits = raw.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("1")) {
    digits = digits.slice(1);
  }
  digits = digits.slice(0, 10);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 6)}-${digits.slice(6)}`;
}

export function phoneDigits(phone: string): string {
  let digits = phone.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("1")) {
    digits = digits.slice(1);
  }
  return digits.slice(0, 10);
}

export function isValidWebUrl(value: string): boolean {
  const raw = value.trim();
  if (!raw) return false;
  try {
    const withScheme = /:\/\//.test(raw) ? raw : `https://${raw}`;
    const url = new URL(withScheme);
    if (url.protocol !== "http:" && url.protocol !== "https:") return false;
    const host = url.hostname.replace(/^www\./, "");
    return host.includes(".");
  } catch {
    return false;
  }
}

export function validateIdentity(
  identity: ProfileIdentity,
  options: { requireContact?: boolean } = {},
): string[] {
  const errors: string[] = [];
  if (options.requireContact) {
    if (!identity.preferred_name.trim()) {
      errors.push("Add the preferred name you want on your resume.");
    }
    if (!identity.email.trim()) {
      errors.push("Add an email address for your resume.");
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(identity.email.trim())) {
      errors.push("Enter a valid email address.");
    }
    if (!phoneDigits(identity.phone)) {
      errors.push("Add a 10-digit phone number.");
    }
  }
  const digits = phoneDigits(identity.phone);
  if (digits.length > 0 && digits.length !== 10) {
    errors.push("Phone number must be 10 digits.");
  }
  for (const link of identity.links) {
    const title = link.title.trim();
    const url = link.url.trim();
    if (!title && !url) continue;
    if (title && !url) {
      errors.push(`Link “${title}” needs a URL.`);
      continue;
    }
    if (url && !isValidWebUrl(url)) {
      errors.push(`“${title || url}” is not a valid web link.`);
    }
  }
  return errors;
}

function isPresetPronoun(value: string): boolean {
  return (PRONOUN_PRESETS as readonly string[]).includes(value);
}

export function ProfileIdentityEditor({ identity, onChange, errors = [] }: Props) {
  const inferredOther = Boolean(identity.pronouns) && !isPresetPronoun(identity.pronouns);
  const [otherMode, setOtherMode] = useState(inferredOther);

  useEffect(() => {
    if (identity.pronouns && !isPresetPronoun(identity.pronouns)) {
      setOtherMode(true);
    }
  }, [identity.pronouns]);

  const selectValue = useMemo(() => {
    if (otherMode) return OTHER;
    if (isPresetPronoun(identity.pronouns)) return identity.pronouns;
    return "";
  }, [identity.pronouns, otherMode]);

  function patch(partial: Partial<ProfileIdentity>) {
    onChange({ ...identity, ...partial });
  }

  function updateLink(index: number, partial: Partial<ProfileWebLink>) {
    const links = identity.links.map((link, idx) =>
      idx === index ? { ...link, ...partial } : link,
    );
    patch({ links });
  }

  return (
    <section className="space-y-3 rounded-[var(--radius-card)] border border-border bg-surface p-4">
      <div>
        <h3 className="text-sm font-semibold text-ink-text">Contact & identity</h3>
        <p className="mt-1 text-xs text-muted">
          Shown at the top of generated resumes. Prefer the name and email you want employers to see.
        </p>
      </div>

      {errors.length > 0 ? (
        <ul className="list-disc space-y-1 rounded-[var(--radius-button)] border border-danger/30 bg-danger-muted/40 px-3 py-2 pl-6 text-xs text-danger">
          {errors.map((msg) => (
            <li key={msg}>{msg}</li>
          ))}
        </ul>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <FieldGroup label="Preferred name (for resume)">
          <FieldInput
            value={identity.preferred_name}
            onChange={(e) => patch({ preferred_name: e.target.value })}
            placeholder="Jordan Lee"
            autoComplete="name"
          />
        </FieldGroup>

        <div className="block space-y-2">
          <FieldGroup label="Pronouns">
            <FieldSelect
              value={selectValue}
              onChange={(e) => {
                const next = e.target.value;
                if (next === OTHER) {
                  setOtherMode(true);
                  if (isPresetPronoun(identity.pronouns)) {
                    patch({ pronouns: "" });
                  }
                  return;
                }
                setOtherMode(false);
                patch({ pronouns: next });
              }}
            >
              <option value="">Select…</option>
              {PRONOUN_PRESETS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
              <option value={OTHER}>Other</option>
            </FieldSelect>
          </FieldGroup>
          {otherMode ? (
            <FieldInput
              value={isPresetPronoun(identity.pronouns) ? "" : identity.pronouns}
              onChange={(e) => patch({ pronouns: e.target.value })}
              placeholder="Enter pronouns"
              autoComplete="off"
            />
          ) : null}
          <label className="flex items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              className="rounded border-border text-brand-strong focus:ring-brand/30"
              checked={identity.show_pronouns}
              onChange={(e) => patch({ show_pronouns: e.target.checked })}
            />
            Show pronouns on resume
          </label>
        </div>

        <FieldGroup label="Email">
          <FieldInput
            type="email"
            value={identity.email}
            onChange={(e) => patch({ email: e.target.value })}
            placeholder="you@example.com"
            autoComplete="email"
          />
        </FieldGroup>

        <FieldGroup label="Phone">
          <div
            className={`flex overflow-hidden ${fieldClass} !p-0 focus-within:border-brand-strong/40 focus-within:ring-2 focus-within:ring-brand/15`}
          >
            <span
              className="flex shrink-0 select-none items-center border-r border-border bg-surface-raised/70 px-3 text-sm font-medium text-muted"
              aria-hidden
            >
              +1
            </span>
            <input
              type="tel"
              inputMode="numeric"
              autoComplete="tel-national"
              className="min-w-0 flex-1 border-0 bg-transparent px-3.5 py-2.5 text-sm text-ink-text outline-none placeholder:text-subtle"
              value={formatPhoneInput(identity.phone)}
              onChange={(e) => patch({ phone: formatPhoneInput(e.target.value) })}
              placeholder="555-555-0100"
              maxLength={12}
              aria-label="Phone number"
            />
          </div>
          <p className="mt-1 text-xs text-subtle">US numbers only — 10 digits with automatic dashes.</p>
        </FieldGroup>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
            Web links
          </p>
          <button
            type="button"
            className={linkClass}
            onClick={() => patch({ links: [...identity.links, emptyLink()] })}
          >
            + Add link
          </button>
        </div>
        <p className="text-xs text-muted">
          Title + URL — e.g. LinkedIn, personal site, portfolio.
        </p>
        {identity.links.length === 0 ? (
          <p className="text-xs text-subtle">No links yet.</p>
        ) : null}
        {identity.links.map((link, index) => {
          const urlError =
            link.url.trim().length > 0 && !isValidWebUrl(link.url)
              ? "Enter a valid URL (https://…)"
              : link.title.trim() && !link.url.trim()
                ? "URL required"
                : null;
          return (
            <div
              key={`link-${index}`}
              className="grid gap-2 rounded-[var(--radius-button)] border border-border-subtle bg-surface-raised/40 p-3 sm:grid-cols-[minmax(0,0.4fr)_minmax(0,1fr)_auto]"
            >
              <FieldGroup label="Title">
                <FieldInput
                  value={link.title}
                  onChange={(e) => updateLink(index, { title: e.target.value })}
                  placeholder="LinkedIn"
                />
              </FieldGroup>
              <FieldGroup label="URL">
                <FieldInput
                  type="url"
                  value={link.url}
                  onChange={(e) => updateLink(index, { url: e.target.value })}
                  placeholder="https://linkedin.com/in/you"
                  aria-invalid={Boolean(urlError)}
                />
                {urlError ? <p className="mt-1 text-xs text-danger">{urlError}</p> : null}
              </FieldGroup>
              <div className="flex items-end pb-0.5">
                <button
                  type="button"
                  className="text-xs font-semibold text-danger hover:underline"
                  onClick={() =>
                    patch({ links: identity.links.filter((_, idx) => idx !== index) })
                  }
                >
                  Remove
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
