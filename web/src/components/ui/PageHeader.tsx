import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}

export function PageHeader({ title, subtitle, action }: PageHeaderProps) {
  return (
    <header className={`mb-6 shrink-0 ${action ? "flex items-start justify-between gap-4" : ""}`}>
      <div>
        <h1 className="font-display text-2xl tracking-tight text-ink-text sm:text-3xl">{title}</h1>
        {subtitle ? <p className="mt-1 max-w-prose text-sm leading-relaxed text-muted">{subtitle}</p> : null}
      </div>
      {action}
    </header>
  );
}
