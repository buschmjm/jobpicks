import { Link } from "react-router-dom";
import { useBilling } from "../hooks/useBilling";
import { creditPoolsFromUsage, CreditWallet } from "./CreditWallet";
import { CheckoutButton } from "./CheckoutButton";

type DeckQuotaPillProps = {
  remaining: number;
  className?: string;
};

export function DeckQuotaPill({ remaining, className = "" }: DeckQuotaPillProps) {
  const { billing } = useBilling();
  const pools = creditPoolsFromUsage(billing?.usage);
  const deckPool = pools.find((p) => p.key === "deck");
  const low = remaining <= 3;

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span
        className={`rounded-full border px-3 py-1 text-xs font-semibold ${
          low
            ? "border-accent/35 bg-accent-muted/60 text-accent-strong"
            : "border-border bg-surface/90 text-muted backdrop-blur-sm"
        }`}
      >
        {remaining} swipe{remaining === 1 ? "" : "s"} left today
      </span>
      {deckPool && billing?.tier === "free" ? (
        <CreditWallet pools={[deckPool]} compact />
      ) : null}
    </div>
  );
}

type DeckMilestoneScreenProps = {
  onRefresh: () => void;
};

export function DeckMilestoneScreen({ onRefresh }: DeckMilestoneScreenProps) {
  const { billing } = useBilling();
  const price = billing?.pro_monthly_price_cents
    ? `$${(billing.pro_monthly_price_cents / 100).toFixed(0)}/mo`
    : "$15/mo";

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-12 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-accent/25 bg-accent-muted text-3xl">
        🎯
      </div>
      <h2 className="font-display text-2xl text-ink-text">You reviewed today&apos;s matches</h2>
      <p className="mt-2 max-w-md text-sm text-muted">
        Great work exploring your deck. Pro shows every ranked match each day plus 20 AI application
        prep packets per month ({price}).
      </p>
      <div className="mt-6 flex flex-col items-center gap-3 sm:flex-row">
        <Link
          to="/todo"
          className="inline-flex items-center justify-center rounded-[var(--radius-button)] border border-brand-deep/10 bg-brand-strong px-5 py-2.5 text-sm font-semibold text-on-brand shadow-sm hover:bg-brand-deep"
        >
          See my application queue →
        </Link>
        {billing?.tier === "free" ? (
          <CheckoutButton
            stripeConfigured={billing.stripe_configured}
            externalCheckoutAllowed={billing.external_checkout_allowed}
            size="md"
            label="Upgrade to Pro"
          />
        ) : null}
        <button
          type="button"
          onClick={onRefresh}
          className="text-sm font-medium text-muted hover:text-ink-text"
        >
          Refresh deck
        </button>
      </div>
    </div>
  );
}
