interface NavIconProps {
  name: "deck" | "swipe" | "apply" | "advisor" | "settings" | "search";
  active?: boolean;
}

export function NavIcon({ name, active = false }: NavIconProps) {
  const className = active ? "text-brand-strong" : "text-subtle";

  if (name === "swipe") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
        <rect x="7" y="4" width="10" height="16" rx="2" stroke="currentColor" strokeWidth="1.75" />
        <path d="M3 12h2M19 12h2" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
      </svg>
    );
  }

  if (name === "settings") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.75" />
        <path
          d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4l1.4-1.4M17 7l1.4-1.4"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  if (name === "deck") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
        <rect x="3" y="5" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.75" />
        <rect x="7" y="9" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.75" />
        <path d="M7 13h10" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
      </svg>
    );
  }

  if (name === "apply") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
        <path
          d="M9 11l2 2 4-4"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <rect x="4" y="4" width="16" height="16" rx="3" stroke="currentColor" strokeWidth="1.75" />
      </svg>
    );
  }

  if (name === "search") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
        <circle cx="11" cy="11" r="6" stroke="currentColor" strokeWidth="1.75" />
        <path d="M16 16l4 4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
      </svg>
    );
  }

  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      <path
        d="M12 3a5 5 0 00-5 5v2H6a2 2 0 00-2 2v7a2 2 0 002 2h12a2 2 0 002-2v-7a2 2 0 00-2-2h-1V8a5 5 0 00-5-5z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      <path d="M9 14h6M9 17h4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
      <circle cx="12" cy="8" r="1.5" fill="currentColor" />
    </svg>
  );
}

export function LoadingSpinner({ label }: { label?: string }) {
  return (
    <div className="text-center">
      <InlineSpinner size="lg" className="mx-auto" />
      {label ? <p className="mt-4 text-sm text-muted">{label}</p> : null}
    </div>
  );
}

export function InlineSpinner({
  size = "sm",
  className = "",
  label = "Loading",
}: {
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
}) {
  const dim = size === "lg" ? "h-11 w-11" : size === "md" ? "h-5 w-5" : "h-4 w-4";
  return (
    <span
      role="status"
      aria-label={label}
      className={`relative inline-block ${dim} ${className}`.trim()}
    >
      <span className="absolute inset-0 rounded-full border-2 border-border" />
      <span className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-brand-strong" />
    </span>
  );
}
