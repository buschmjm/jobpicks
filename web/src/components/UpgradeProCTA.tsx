import { CheckoutButton, ViewPlansLink } from "./CheckoutButton";
import { Alert } from "./ui/Alert";

type UpgradeProCTAProps = {
  used: number;
  limit: number;
  stripeConfigured: boolean;
  externalCheckoutAllowed?: boolean;
  className?: string;
};

export function UpgradeProCTA({
  used,
  limit,
  stripeConfigured,
  externalCheckoutAllowed = true,
  className = "",
}: UpgradeProCTAProps) {
  return (
    <Alert tone="warning" className={className}>
      <p className="font-semibold text-ink-text">AI application packet limit reached</p>
      <p className="mt-2 text-sm text-muted">
        Free accounts include {limit} lifetime AI application packets
        {used > 0 ? ` — you've used ${used}` : ""}. Upgrade to Pro for 20 packets per month,
        all available daily matches, and full score breakdowns.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <CheckoutButton
          stripeConfigured={stripeConfigured}
          externalCheckoutAllowed={externalCheckoutAllowed}
        />
        <ViewPlansLink />
      </div>
    </Alert>
  );
}
