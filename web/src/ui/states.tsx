import type { ReactNode } from "react";

type BannerTone = "info" | "warning" | "error";

const BANNER_TONE_CLASS: Record<BannerTone, string> = {
  info: "border-accent/60 bg-accent/10",
  warning: "border-dev-missed/60 bg-dev-missed/10",
  error: "border-error/60 bg-error/10",
};

export interface BannerProps {
  tone?: BannerTone;
  children: ReactNode;
  action?: ReactNode;
}

/** Inline message banner: info/warning are polite, errors are assertive (UI spec §6/§8). */
export function Banner({ tone = "info", children, action }: BannerProps) {
  const role = tone === "error" ? "alert" : "status";
  return (
    <div
      role={role}
      className={`flex items-start gap-3 rounded-control border px-4 py-3 text-control ${BANNER_TONE_CLASS[tone]}`}
    >
      <p className="m-0 flex-1">{children}</p>
      {action}
    </div>
  );
}

export interface EmptyStateProps {
  title: string;
  help: string;
  action?: ReactNode;
}

/** Empty state: one-line title, one-line help, optional primary action (UI spec §6). */
export function EmptyState({ title, help, action }: EmptyStateProps) {
  return (
    <section className="rounded-card border border-border bg-surface p-6">
      <h2 className="m-0 text-h3 font-semibold">{title}</h2>
      <p className="mt-2 mb-4 text-muted">{help}</p>
      {action}
    </section>
  );
}

export interface LoadingStateProps {
  label?: string;
}

/** Polite live region while data loads (UI spec §8). */
export function LoadingState({ label = "Loading…" }: LoadingStateProps) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-3 text-muted">
      <span
        aria-hidden="true"
        className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-border-strong border-t-accent motion-reduce:animate-none"
      />
      <span>{label}</span>
    </div>
  );
}
