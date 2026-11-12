import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
  children: ReactNode;
}

export function Chip({ active = false, className = "", children, ...props }: ChipProps) {
  return (
    <button
      type="button"
      className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
        active
          ? "border-transparent bg-brand-strong text-on-brand shadow-sm"
          : "border border-border bg-surface text-muted hover:border-border-subtle hover:text-ink-text"
      } ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
