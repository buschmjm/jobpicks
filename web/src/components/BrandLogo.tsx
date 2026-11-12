interface BrandLogoProps {
  size?: "sm" | "md" | "lg";
  showWordmark?: boolean;
  className?: string;
}

const sizes = {
  sm: { icon: 28, wordmark: "text-lg" },
  md: { icon: 32, wordmark: "text-xl" },
  lg: { icon: 48, wordmark: "text-3xl" },
} as const;

export function BrandLogo({
  size = "md",
  showWordmark = true,
  className = "",
}: BrandLogoProps) {
  const { icon, wordmark } = sizes[size];

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <svg
        width={icon}
        height={icon}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
        className="shrink-0"
      >
        <rect x="8" y="10" width="28" height="20" rx="4" fill="#fafaf9" stroke="#e7e5e4" strokeWidth="1.5" />
        <rect x="12" y="16" width="28" height="20" rx="4" fill="#ffffff" stroke="#292524" strokeWidth="1.5" />
        <rect x="16" y="22" width="28" height="20" rx="4" fill="#f5f5f4" stroke="#e7e5e4" strokeWidth="1.5" />
        <path d="M16 28h20" stroke="#b45309" strokeWidth="2" strokeLinecap="round" />
        <path d="M16 33h14" stroke="#a8a29e" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      {showWordmark ? (
        <span className={`font-display leading-none tracking-tight text-ink-text ${wordmark}`}>
          Job<span className="text-accent">Picks</span>
        </span>
      ) : null}
    </div>
  );
}

export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <div
      className={`inline-flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-surface shadow-sm ${className}`}
    >
      <svg width="22" height="22" viewBox="0 0 48 48" fill="none" aria-hidden>
        <rect x="10" y="14" width="22" height="16" rx="3" fill="#ffffff" stroke="#e7e5e4" />
        <rect x="14" y="18" width="22" height="16" rx="3" fill="#fafaf9" stroke="#292524" strokeWidth="1.5" />
        <path d="M14 24h16" stroke="#b45309" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  );
}
