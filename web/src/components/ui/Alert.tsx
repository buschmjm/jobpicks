import type { ReactNode } from "react";

type AlertTone = "error" | "warning" | "info" | "success";

interface AlertProps {
  tone?: AlertTone;
  children: ReactNode;
  className?: string;
}

const toneClasses: Record<AlertTone, string> = {
  error: "border-red-200 bg-danger-muted text-red-800",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  info: "border-border bg-surface-raised text-muted",
  success: "border-emerald-200 bg-success-muted text-success",
};

export function Alert({ tone = "info", children, className = "" }: AlertProps) {
  return (
    <p className={`rounded-[var(--radius-button)] border px-4 py-3 text-sm leading-relaxed ${toneClasses[tone]} ${className}`}>
      {children}
    </p>
  );
}

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="mt-12 text-center">
      {icon ? (
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-surface text-brand-strong shadow-sm">
          {icon}
        </div>
      ) : null}
      <p className="text-lg font-semibold text-ink-text">{title}</p>
      {description ? <p className="mx-auto mt-2 max-w-sm text-sm text-muted">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

interface SurfaceCardProps {
  children: ReactNode;
  className?: string;
  padding?: "sm" | "md" | "lg";
}

const paddingClasses = {
  sm: "p-3",
  md: "p-4",
  lg: "p-5",
};

export function SurfaceCard({ children, className = "", padding = "md" }: SurfaceCardProps) {
  return (
    <div
      className={`rounded-[var(--radius-card)] border border-border bg-surface shadow-[0_4px_24px_-8px_rgba(15,23,42,0.08)] ${paddingClasses[padding]} ${className}`}
    >
      {children}
    </div>
  );
}
