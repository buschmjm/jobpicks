import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "success";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  children: ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "border border-brand-deep/10 bg-brand-strong text-on-brand shadow-[0_2px_8px_-2px_rgba(28,25,23,0.35)] hover:bg-brand-deep active:scale-[0.98]",
  secondary:
    "border border-border bg-surface text-ink-text shadow-sm hover:border-muted hover:bg-surface-raised active:scale-[0.98]",
  ghost:
    "border border-transparent bg-transparent text-muted hover:bg-surface-overlay hover:text-ink-text",
  danger:
    "border border-danger/20 bg-danger-muted text-danger hover:bg-red-100 active:scale-[0.98]",
  success:
    "border border-success/25 bg-success-muted text-success hover:bg-green-100 active:scale-[0.98]",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-sm rounded-lg",
  md: "px-4 py-2.5 text-sm rounded-[var(--radius-button)]",
  lg: "px-5 py-3.5 text-base rounded-[var(--radius-button)]",
};

export function Button({
  variant = "primary",
  size = "md",
  fullWidth = false,
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${variantClasses[variant]} ${sizeClasses[size]} ${fullWidth ? "w-full" : ""} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
