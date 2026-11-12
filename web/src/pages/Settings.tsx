import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { AddressAutocomplete } from "../components/AddressAutocomplete";
import { TitlePicker } from "../components/TitlePicker";
import { TitleSuggestions } from "../components/TitleSuggestions";
import { PlanDetailsPanel } from "../components/PlanDetailsPanel";
import { Button } from "../components/ui/Button";
import { Alert } from "../components/ui/Alert";
import { FieldGroup, FieldInput, FieldSelect, FieldTextarea } from "../components/ui/Field";
import { PageHeader } from "../components/ui/PageHeader";
import { useAuth } from "../context/AuthContext";
import { useGoogleMapsApiKey } from "../hooks/useGoogleMapsApiKey";
import { openExternalUrl } from "../lib/openExternalUrl";
import type {
  BillingStatus,
  EmailPreferences,
  JobTitle,
  ReferralStatus,
  RemoteOpenness,
  SavedApplicationAnswer,
  UserPreferences,
} from "../types";

export function SettingsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { signOut } = useAuth();
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);
  const [targetTitles, setTargetTitles] = useState<JobTitle[]>([]);
  const [homeLocation, setHomeLocation] = useState("");
  const [homeLat, setHomeLat] = useState<number | null>(null);
  const [homeLon, setHomeLon] = useState<number | null>(null);
  const googleMapsApiKey = useGoogleMapsApiKey();
  const [maxCommute, setMaxCommute] = useState("45");
  const [remoteOpenness, setRemoteOpenness] = useState<RemoteOpenness>("open_to_remote");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [vaultItems, setVaultItems] = useState<SavedApplicationAnswer[]>([]);
  const [vaultLoading, setVaultLoading] = useState(true);
  const [vaultSavingKey, setVaultSavingKey] = useState<string | null>(null);
  const [vaultDrafts, setVaultDrafts] = useState<Record<string, string>>({});
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [billingLoading, setBillingLoading] = useState(true);
  const [billingBusy, setBillingBusy] = useState(false);
  const [referral, setReferral] = useState<ReferralStatus | null>(null);
  const [referralLoading, setReferralLoading] = useState(true);
  const [referralCodeInput, setReferralCodeInput] = useState("");
  const [referralBusy, setReferralBusy] = useState(false);
  const [emailPrefs, setEmailPrefs] = useState<EmailPreferences | null>(null);
  const [emailStatus, setEmailStatus] = useState<import("../types").EmailStatus | null>(null);
  const [emailLoading, setEmailLoading] = useState(true);
  const [emailBusy, setEmailBusy] = useState(false);
  const [copiedReferral, setCopiedReferral] = useState(false);
  const [privacyBusy, setPrivacyBusy] = useState(false);

  useEffect(() => {
    const billingResult = searchParams.get("billing");
    if (billingResult === "success") {
      setMessage("Welcome to Pro! Your plan is now active.");
      setSearchParams({}, { replace: true });
      void api.billing.status().then(setBilling).catch(() => undefined);
    } else if (billingResult === "canceled") {
      setMessage("Checkout canceled — no changes were made.");
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.preferences.get();
        setPrefs(data);
        const resolved = await api.titles.resolve(data.target_titles ?? []);
        setTargetTitles(resolved.items);
        setHomeLocation(data.home_location ?? "");
        setHomeLat(data.home_lat ?? null);
        setHomeLon(data.home_lon ?? null);
        setMaxCommute(String(data.max_commute_minutes ?? 45));
        setRemoteOpenness(data.remote_openness);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load preferences");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    void (async () => {
      setBillingLoading(true);
      try {
        setBilling(await api.billing.status());
      } catch {
        /* optional section */
      } finally {
        setBillingLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    void (async () => {
      setReferralLoading(true);
      try {
        setReferral(await api.referrals.status());
      } catch {
        /* optional section */
      } finally {
        setReferralLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    void (async () => {
      setEmailLoading(true);
      try {
        const [prefs, status] = await Promise.all([
          api.email.preferences(),
          api.email.status().catch(() => null),
        ]);
        setEmailPrefs(prefs);
        setEmailStatus(status);
      } catch {
        /* optional section */
      } finally {
        setEmailLoading(false);
      }
    })();
  }, []);

  async function startCheckout() {
    setBillingBusy(true);
    setError(null);
    try {
      const res = await api.billing.checkout();
      await openExternalUrl(res.checkout_url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start checkout");
      setBillingBusy(false);
    }
  }

  async function openPortal() {
    setBillingBusy(true);
    setError(null);
    try {
      const res = await api.billing.portal();
      await openExternalUrl(res.portal_url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open billing portal");
      setBillingBusy(false);
    }
  }

  async function cancelSubscription() {
    if (!window.confirm("Cancel Pro at the end of your current billing period?")) return;
    setBillingBusy(true);
    setError(null);
    try {
      await api.billing.cancel();
      setBilling(await api.billing.status());
      setMessage("Pro will remain active until the end of your billing period.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not cancel subscription");
    } finally {
      setBillingBusy(false);
    }
  }

  async function applyReferralCode(e: FormEvent) {
    e.preventDefault();
    const code = referralCodeInput.trim();
    if (!code) return;
    setReferralBusy(true);
    setError(null);
    try {
      setReferral(await api.referrals.apply(code));
      setReferralCodeInput("");
      setMessage("Referral code applied.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Invalid referral code");
    } finally {
      setReferralBusy(false);
    }
  }

  async function copyReferralLink() {
    if (!referral?.share_url) return;
    try {
      await navigator.clipboard.writeText(referral.share_url);
      setCopiedReferral(true);
      window.setTimeout(() => setCopiedReferral(false), 2000);
    } catch {
      setError("Could not copy link to clipboard");
    }
  }

  async function toggleDigest(enabled: boolean) {
    setEmailBusy(true);
    setError(null);
    try {
      if (enabled) {
        setEmailPrefs(await api.email.resubscribe());
        setMessage("Daily digest emails re-enabled.");
      } else {
        setEmailPrefs(await api.email.unsubscribe());
        setMessage("Daily digest emails turned off.");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update email preferences");
    } finally {
      setEmailBusy(false);
    }
  }

  useEffect(() => {
    void (async () => {
      setVaultLoading(true);
      try {
        const res = await api.applicationAnswers.list();
        setVaultItems(res.items);
        setVaultDrafts(
          Object.fromEntries(res.items.map((item) => [item.question_key, item.answer])),
        );
      } catch {
        /* optional section */
      } finally {
        setVaultLoading(false);
      }
    })();
  }, []);

  async function saveVaultItem(item: SavedApplicationAnswer) {
    setVaultSavingKey(item.question_key);
    setError(null);
    try {
      const answer = (vaultDrafts[item.question_key] ?? item.answer).trim();
      const updated = await api.applicationAnswers.upsert(item.question_key, {
        question_text: item.question_text,
        answer,
      });
      setVaultItems((prev) =>
        prev.map((row) => (row.question_key === updated.question_key ? updated : row)),
      );
      setMessage("Saved application answer updated.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save application answer");
    } finally {
      setVaultSavingKey(null);
    }
  }

  async function deleteVaultItem(questionKey: string) {
    setError(null);
    try {
      await api.applicationAnswers.delete(questionKey);
      setVaultItems((prev) => prev.filter((row) => row.question_key !== questionKey));
      setVaultDrafts((prev) => {
        const next = { ...prev };
        delete next[questionKey];
        return next;
      });
      setMessage("Application answer removed from vault.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete application answer");
    }
  }

  async function handleExportData() {
    setPrivacyBusy(true);
    setError(null);
    try {
      const payload = await api.privacy.export();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `jobpicks-export-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setMessage("Your data export downloaded.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to export data");
    } finally {
      setPrivacyBusy(false);
    }
  }

  async function handleDeleteAccount() {
    const confirmed = window.confirm(
      "Permanently delete your account and all personal data? This cannot be undone.",
    );
    if (!confirmed) return;

    setPrivacyBusy(true);
    setError(null);
    try {
      await api.privacy.deleteMyData();
      await signOut();
      navigate("/login", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete account");
      setPrivacyBusy(false);
    }
  }

  async function addSuggestedTitle(title: string) {
    try {
      const created = await api.titles.create(title);
      setTargetTitles((prev) => {
        if (prev.some((item) => item.id === created.id || item.normalized_name === created.normalized_name)) {
          return prev;
        }
        return [...prev, created];
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add title");
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const res = await api.preferences.update({
        target_titles: targetTitles.map((title) => title.name),
        home_location: homeLocation.trim() || null,
        home_lat: homeLat,
        home_lon: homeLon,
        max_commute_minutes:
          remoteOpenness === "remote_only" ? null : parseInt(maxCommute, 10) || 45,
        remote_openness: remoteOpenness,
      });
      setPrefs(res.preferences);
      const resolved = await api.titles.resolve(res.preferences.target_titles ?? []);
      setTargetTitles(resolved.items);
      setMessage(res.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save preferences");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="text-muted">Loading preferences…</p>;
  }

  return (
    <div className="pb-2">
      <PageHeader
        title="Preferences"
        subtitle="Set your target roles, home location, commute budget, and remote work openness."
      />

      {error ? <Alert tone="error" className="mb-4">{error}</Alert> : null}
      {message ? <Alert tone="success" className="mb-4">{message}</Alert> : null}

      {prefs?.geocode_status === "failed" ? (
        <Alert tone="warning" className="mb-4">
          We could not geocode your home address. Commute filtering may be limited until a valid US
          address is saved.
        </Alert>
      ) : null}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <TitlePicker titles={targetTitles} onChange={setTargetTitles} />
          <TitleSuggestions
            selected={targetTitles}
            onAddTitle={(title) => void addSuggestedTitle(title)}
          />
        </div>

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
            Used to estimate drive time to onsite and hybrid jobs.
            {googleMapsApiKey ? " Pick an address from the suggestions for best accuracy." : ""}
          </p>
        </FieldGroup>

        <FieldGroup label="Work location preference">
          <FieldSelect
            value={remoteOpenness}
            onChange={(e) => setRemoteOpenness(e.target.value as RemoteOpenness)}
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

        <Button type="submit" fullWidth size="lg" disabled={saving || targetTitles.length === 0}>
          {saving ? "Saving…" : "Save preferences"}
        </Button>
      </form>

      <div className="mt-10">
        <PageHeader
          title="JobPicks Pro"
          subtitle="More daily matches, full explanations, score breakdowns, and intraday alerts."
        />
        {billingLoading ? (
          <p className="text-sm text-muted">Loading subscription…</p>
        ) : billing ? (
          <PlanDetailsPanel
            billing={billing}
            billingBusy={billingBusy}
            compact
            onUpgrade={() => void startCheckout()}
            onManageBilling={() => void openPortal()}
            onCancel={() => void cancelSubscription()}
          />
        ) : (
          <p className="text-sm text-muted">Could not load plan details.</p>
        )}
        {!billingLoading && billing && !billing.stripe_configured ? (
          <p className="mt-2 text-xs text-subtle">Billing is not configured in this environment.</p>
        ) : null}
      </div>

      <div className="mt-10">
        <PageHeader
          title="Referrals"
          subtitle={`Give friends ${referral?.reward_days ?? 90} days of Pro — you earn the same when they join.`}
        />
        {referralLoading ? (
          <p className="text-sm text-muted">Loading referral info…</p>
        ) : referral ? (
          <div className="mt-4 space-y-4 rounded-[var(--radius-card)] border border-border bg-surface-raised p-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">Your code</p>
              <p className="mt-1 font-mono text-lg font-semibold text-ink-text">{referral.referral_code}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => void copyReferralLink()}>
                  {copiedReferral ? "Copied!" : "Copy invite link"}
                </Button>
              </div>
            </div>
            <p className="text-sm text-muted">
              {referral.successful_referrals} successful referral
              {referral.successful_referrals === 1 ? "" : "s"}
              {referral.referred_by_applied ? " · You joined with a referral code" : ""}
            </p>
            {!referral.referred_by_applied ? (
              <form onSubmit={applyReferralCode} className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <FieldGroup label="Have a referral code?">
                  <FieldInput
                    value={referralCodeInput}
                    onChange={(e) => setReferralCodeInput(e.target.value)}
                    placeholder="Enter code"
                  />
                </FieldGroup>
                <Button type="submit" size="sm" disabled={referralBusy || !referralCodeInput.trim()}>
                  {referralBusy ? "Applying…" : "Apply code"}
                </Button>
              </form>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-muted">Referral details unavailable.</p>
        )}
      </div>

      <div className="mt-10">
        <PageHeader
          title="Email digest"
          subtitle="Daily summary of new matches, delivered around 6 AM in your timezone."
        />
        {emailLoading ? (
          <p className="text-sm text-muted">Loading email preferences…</p>
        ) : emailPrefs ? (
          <div className="mt-4 rounded-[var(--radius-card)] border border-border bg-surface-raised p-4">
            <p className="text-sm text-ink-text">
              Daily digest:{" "}
              <span className="font-semibold">
                {emailPrefs.digest_enabled ? "On" : "Off"}
              </span>
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {!emailPrefs.digest_enabled ? (
                <Button size="sm" disabled={emailBusy} onClick={() => void toggleDigest(true)}>
                  {emailBusy ? "Saving…" : "Re-enable digest"}
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={emailBusy}
                  onClick={() => void toggleDigest(false)}
                >
                  {emailBusy ? "Saving…" : "Turn off digest"}
                </Button>
              )}
            </div>
            {emailStatus && !emailStatus.ready ? (
              <p className="mt-3 text-xs text-subtle">
                SMTP is not fully configured in this environment — digests will not send until
                SMTP_HOST, SMTP_USER, and SMTP_PASSWORD are set in cluster secrets.
              </p>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-muted">Email preferences unavailable.</p>
        )}
      </div>

      <div className="mt-10">
        <PageHeader
          title="Application answers"
          subtitle="Reusable screening responses saved from your prepare flow."
        />
        {vaultLoading ? (
          <p className="text-sm text-muted">Loading saved answers…</p>
        ) : vaultItems.length === 0 ? (
          <p className="text-sm text-muted">
            No saved answers yet. Confirm answers on the Prepare screen to build your vault.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {vaultItems.map((item) => (
              <li
                key={item.question_key}
                className="rounded-[var(--radius-button)] border border-border bg-surface-raised p-3"
              >
                <p className="text-sm font-semibold text-ink-text">{item.question_text}</p>
                <p className="mt-1 text-xs text-subtle">{item.question_key}</p>
                <FieldTextarea
                  className="mt-3"
                  rows={3}
                  value={vaultDrafts[item.question_key] ?? item.answer}
                  onChange={(event) =>
                    setVaultDrafts((prev) => ({
                      ...prev,
                      [item.question_key]: event.target.value,
                    }))
                  }
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    disabled={vaultSavingKey === item.question_key}
                    onClick={() => void saveVaultItem(item)}
                  >
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void deleteVaultItem(item.question_key)}
                  >
                    Remove
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-10">
        <PageHeader
          title="Privacy"
          subtitle="Export or delete your personal data. See our privacy policy for retention details."
        />
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={privacyBusy}
            onClick={() => void handleExportData()}
          >
            {privacyBusy ? "Working…" : "Download my data"}
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={privacyBusy}
            onClick={() => void handleDeleteAccount()}
          >
            Delete account
          </Button>
          <a
            href="/privacy"
            className="inline-flex items-center rounded-[var(--radius-button)] px-3 py-2 text-sm font-semibold text-brand-strong hover:text-brand-deep"
          >
            Privacy policy
          </a>
        </div>
      </div>
    </div>
  );
}
