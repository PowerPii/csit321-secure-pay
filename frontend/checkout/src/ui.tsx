import type { ReactNode } from "react";

export function Field({ label, error, id, children }: { label: string; error?: string; id: string; children: ReactNode }) {
  return (
    <div className={`field${error ? " has-error" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
      {error && <span className="error" role="alert">{error}</span>}
    </div>
  );
}

export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

