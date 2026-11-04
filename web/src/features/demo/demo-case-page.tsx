import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, createApiClient, getDemoCase, type ApiClient } from "../../api";
import { Banner, EmptyState, LoadingState } from "../../ui/states";
import { ReviewSurface } from "../review/player/review-surface";
import { toDemoCaseDetail, type DemoCaseDetail } from "./cases";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export interface DemoCasePageProps {
  client?: ApiClient;
}

/** `/demo/:caseId`: the review core loaded with frozen data from the local API. */
export function DemoCasePage({ client }: DemoCasePageProps = {}) {
  const { caseId = "" } = useParams();
  const [demoCase, setDemoCase] = useState<DemoCaseDetail | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const api = client ?? createApiClient({ baseUrl: API_BASE });
    let cancelled = false;

    getDemoCase(api, caseId)
      .then((payload) => {
        if (!cancelled) setDemoCase(toDemoCaseDetail(payload));
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(caught instanceof Error ? caught : new Error("The demo case could not be loaded."));
      });

    return () => {
      cancelled = true;
    };
  }, [caseId, client]);

  const backLink = (
    <Link to="/demo" className="inline-block text-small text-accent underline underline-offset-4">
      All demo cases
    </Link>
  );

  if (error) {
    if (error instanceof ApiError && error.code === "not_found") {
      return (
        <EmptyState
          title="Case not found"
          help="That demo case is not part of the frozen set."
          action={backLink}
        />
      );
    }
    return (
      <Banner tone="error">
        {error.message} {backLink}
      </Banner>
    );
  }

  if (demoCase === null) {
    return <LoadingState label="Loading demo case…" />;
  }

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="m-0 text-h2 font-semibold">{demoCase.title}</h2>
        <span className="rounded-chip border border-illustration px-2 py-0.5 text-small text-illustration">
          Offline
        </span>
      </header>

      <p className="m-0 text-small text-muted">
        {demoCase.domain} · {demoCase.description}
      </p>

      {backLink}

      <ReviewSurface
        src={`${API_BASE}/demo/cases/${demoCase.id}/${demoCase.media_path}`}
        data={demoCase.data}
      />
    </section>
  );
}
