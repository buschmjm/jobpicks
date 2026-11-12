import { Link } from "react-router-dom";
import { useBilling } from "../hooks/useBilling";
import { UsageMeter } from "./UsageLimits";

/** Compact plan + usage summary shown to signed-in users in the app shell. */
export function PlanStatusBanner() {
  const { billing, loading } = useBilling();

  if (loading || !billing?.usage) {
    return null;
  }

  const isPro = billing.tier === "pro";
  const deck = billing.usage.deck_matches;
  const deckLow =
    deck.limit != null && !deck.unlimited && (deck.remaining ?? 0) <= 3;

  return (
    <div
      className={`mb-4 rounded-xl border px-3 py-2.5 text-sm ${
        isPro
          ? "border-brand-strong/25 bg-brand-muted/30"
          : deckLow
            ? "border-accent/30 bg-brand-muted/50"
            : "border-border-subtle bg-surface-raised/80"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold text-ink-text">
          {isPro ? (
            <>
              <span className="text-brand-strong">Pro</span>
              <span className="ml-2 font-normal text-muted">
                Unlimited advisor &amp; resume · {deck.used}/{deck.limit} deck matches today
              </span>
            </>
          ) : (
            <>
              <span className="text-muted">Free plan</span>
              <span className="ml-2 font-normal text-muted">
                {deck.remaining ?? 0} deck matches left today
              </span>
            </>
          )}
        </p>
        <Link
          to="/settings"
          className="text-xs font-semibold text-brand-strong hover:text-brand-deep"
        >
          {isPro ? "View usage" : "Upgrade"}
        </Link>
      </div>
      {!isPro ? (
        <div className="mt-2 grid gap-1 sm:grid-cols-2">
          <UsageMeter label="Advisor" quota={billing.usage.advisor_messages} />
          <UsageMeter label="Resume builder" quota={billing.usage.resume_builder_messages} />
        </div>
      ) : null}
    </div>
  );
}
