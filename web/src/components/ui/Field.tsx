import { forwardRef, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface FieldLabelProps {
  children: ReactNode;
  htmlFor?: string;
}

export function FieldLabel({ children, htmlFor }: FieldLabelProps) {
  return (
    <span className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
      {htmlFor ? <label htmlFor={htmlFor}>{children}</label> : children}
    </span>
  );
}

const fieldClass =
  "mt-1.5 w-full rounded-[var(--radius-button)] border border-border bg-surface px-3.5 py-2.5 text-sm text-ink-text placeholder:text-subtle focus:border-brand-strong/40 focus:outline-none focus:ring-2 focus:ring-brand/15 read-only:bg-surface-overlay read-only:text-muted read-only:focus:border-border read-only:focus:ring-0";

export const FieldInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function FieldInput(props, ref) {
    return <input {...props} ref={ref} className={`${fieldClass} ${props.className ?? ""}`} />;
  },
);

export function FieldSelect(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${fieldClass} ${props.className ?? ""}`} />;
}

export const FieldTextarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function FieldTextarea(props, ref) {
    return <textarea {...props} ref={ref} className={`${fieldClass} ${props.className ?? ""}`} />;
  },
);

interface FieldGroupProps {
  label: string;
  children: ReactNode;
}

export function FieldGroup({ label, children }: FieldGroupProps) {
  return (
    <div className="block">
      <FieldLabel>{label}</FieldLabel>
      {children}
    </div>
  );
}
