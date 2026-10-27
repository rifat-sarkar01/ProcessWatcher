import { useId, useState } from "react";

export interface AccessGateProps {
  /** Called with the trimmed code once it passes local validation. */
  onSubmit: (code: string) => void;
  /** Server-side rejection (e.g. 401 from the API), shown as an alert. */
  error?: string | null;
  busy?: boolean;
}

const MIN_LENGTH = 4;

const FIELD_CLASS =
  "mt-2 w-full rounded-control border border-border-strong bg-bg px-3 py-2 text-control text-fg placeholder:text-muted/60";

/**
 * Access-code gate (02_AppFlow §7 "access gate").
 *
 * The gate is a UX affordance only: the API enforces the code on every `/runs/*`
 * and `/sop/*` route (05_Schema §13). Nothing here is a security boundary.
 */
export function AccessGate({ onSubmit, error = null, busy = false }: AccessGateProps) {
  const [code, setCode] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const inputId = useId();
  const errorId = useId();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = code.trim();
    if (trimmed.length < MIN_LENGTH) {
      setLocalError(`Enter the access code you were given (at least ${MIN_LENGTH} characters).`);
      return;
    }
    setLocalError(null);
    onSubmit(trimmed);
  }

  const shownError = localError ?? error;

  return (
    <form
      aria-labelledby={`${inputId}-title`}
      onSubmit={handleSubmit}
      noValidate
      className="rounded-card border border-border bg-surface p-6"
    >
      <h2 id={`${inputId}-title`} className="m-0 text-h3 font-semibold">
        Access code required
      </h2>
      <p className="mt-2 mb-6 text-muted">
        This demo is access-gated so model spend stays under control. The code is in your
        submission confirmation.
      </p>

      <label htmlFor={inputId} className="text-control font-medium">
        Access code
      </label>
      <input
        id={inputId}
        name="access-code"
        type="password"
        autoComplete="off"
        className={FIELD_CLASS}
        value={code}
        onChange={(event) => setCode(event.target.value)}
        aria-invalid={shownError ? true : undefined}
        aria-describedby={shownError ? errorId : undefined}
      />

      {shownError ? (
        <p id={errorId} role="alert" className="mt-2 mb-0 text-small text-error">
          {shownError}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={busy}
        aria-disabled={busy || undefined}
        className="mt-6 min-h-11 rounded-control bg-accent px-4 text-control font-medium text-accent-ink disabled:opacity-50"
      >
        {busy ? "Checking…" : "Continue"}
      </button>
    </form>
  );
}
