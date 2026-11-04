import { useEffect, useState } from "react";

import { createApiClient, listDemoCases, type ApiClient } from "../../api";
import { Banner, EmptyState, LoadingState } from "../../ui/states";
import { toDemoCase, type DemoCase } from "./cases";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export interface DemoGalleryProps {
  onOpen: (caseId: string) => void;
  client?: ApiClient;
}

function findingCount(count: number): string {
  return `${count} finding${count === 1 ? "" : "s"}`;
}

function durationLabel(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

/**
 * `/demo`: the frozen cases served by the local API (FR-14).
 *
 * "Offline" is a promise, not decoration: the API reads committed, checksummed files,
 * so the demo keeps working with no outbound network and no model spend.
 */
export function DemoGallery({ onOpen, client }: DemoGalleryProps) {
  const [cases, setCases] = useState<readonly DemoCase[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const api = client ?? createApiClient({ baseUrl: API_BASE });
    let cancelled = false;

    listDemoCases(api)
      .then((summaries) => {
        if (!cancelled) setCases(summaries.map(toDemoCase));
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "The demo cases could not be loaded.");
      });

    return () => {
      cancelled = true;
    };
  }, [client]);

  const header = (
    <header className="flex flex-wrap items-center gap-3">
      <h2 className="m-0 text-h2 font-semibold">Demo cases</h2>
      <span className="rounded-chip border border-illustration px-2 py-0.5 text-small text-illustration">
        Offline
      </span>
    </header>
  );

  if (error) {
    return (
      <section className="space-y-4">
        {header}
        <Banner tone="error">{error}</Banner>
      </section>
    );
  }

  if (cases === null) {
    return (
      <section className="space-y-4">
        {header}
        <LoadingState label="Loading demo cases…" />
      </section>
    );
  }

  if (cases.length === 0) {
    return (
      <EmptyState
        title="No demo cases"
        help="Frozen demo cases are produced by pw demo-build (T-7.1)."
      />
    );
  }

  return (
    <section className="space-y-4">
      {header}

      <p className="m-0 max-w-3xl text-muted">
        Three frozen cases read from the local API, with <strong>no outbound network or model calls</strong>,
        so the demo cannot fail on stage.
      </p>

      <ul className="m-0 grid list-none gap-3 p-0 md:grid-cols-2 xl:grid-cols-3">
        {cases.map((demoCase) => (
          <li key={demoCase.id}>
            <button
              type="button"
              onClick={() => onOpen(demoCase.id)}
              className="h-full w-full rounded-card border border-border bg-surface p-4 text-left transition-colors duration-fast hover:bg-surface-2"
            >
              <span className="text-small uppercase tracking-wide text-muted">
                {demoCase.domain}
              </span>
              <span className="mt-1 block text-h3 font-semibold">{demoCase.title}</span>
              <span className="mt-2 block text-small text-muted">{demoCase.description}</span>
              <span className="mt-3 block font-mono text-small text-muted">
                {findingCount(demoCase.finding_count)} · {durationLabel(demoCase.duration_s)} min
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
