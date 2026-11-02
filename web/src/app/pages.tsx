import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { createApiClient, readStoredAccessCode, storeAccessCode } from "../api";
import { DemoGallery } from "../features/demo/demo-gallery";
import { RunProgress } from "../features/progress/progress-view";
import { DeviationPanel } from "../features/review/panel/deviation-panel";
import type { ReviewDecision } from "../features/review/panel/panel-data";
import { ReviewSurface } from "../features/review/player/review-surface";
import { toTimelineData } from "../features/review/timeline/data";
import { UploadPage } from "../features/upload/upload-page";
import type { Report } from "../types/generated/report";
import { AccessGate } from "../ui/access-gate";
import { Banner, EmptyState, LoadingState } from "../ui/states";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const POLL_MS = 400;

/** Landing screen: access gate first, then the upload + SOP review flow. */
export function HomePage() {
  const [accessCode, setAccessCode] = useState<string | null>(() => readStoredAccessCode());
  const navigate = useNavigate();

  if (!accessCode) {
    return (
      <div className="mx-auto max-w-xl">
        <AccessGate
          onSubmit={(code) => {
            storeAccessCode(code);
            setAccessCode(code);
          }}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex justify-end">
        <button
          type="button"
          className="min-h-11 rounded-control border border-border-strong px-4 text-control"
          onClick={() => {
            storeAccessCode(null);
            setAccessCode(null);
          }}
        >
          Change access code
        </button>
      </div>
      <UploadPage
        accessCode={accessCode}
        baseUrl={API_BASE}
        onStarted={(runId) => navigate(`/runs/${runId}`)}
      />
    </div>
  );
}

type RunStatus = "loading" | "running" | "done" | "error";

interface RunDetail {
  run_id: string;
  status: string;
}

/** Run review screen: live progress until the report is ready, then the review core. */
export function RunPage() {
  const { runId = "" } = useParams();
  const [accessCode, setAccessCode] = useState<string | null>(() => readStoredAccessCode());
  const [status, setStatus] = useState<RunStatus>("loading");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId || !accessCode) return;
    const client = createApiClient({ baseUrl: API_BASE, accessCode });
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    async function tick() {
      try {
        const detail = await client.get<RunDetail>(`/runs/${runId}`);
        if (cancelled) return;
        if (detail.status === "done") {
          const loaded = await client.get<Report>(`/runs/${runId}/report`);
          if (cancelled) return;
          setReport(loaded);
          setStatus("done");
          if (timer) clearInterval(timer);
        } else {
          setStatus("running");
        }
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "The run could not be loaded.");
        setStatus("error");
        if (timer) clearInterval(timer);
      }
    }

    void tick();
    timer = setInterval(() => {
      void tick();
    }, POLL_MS);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [accessCode, runId]);

  const decide = useCallback(
    (deviationId: string, decision: ReviewDecision) => {
      if (!accessCode) return;
      void fetch(`${API_BASE}/runs/${runId}/review`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-Access-Code": accessCode,
        },
        body: JSON.stringify({ deviation_id: deviationId, decision }),
      }).catch(() => {
        // The panel keeps the local decision; a failed save is retried on the next click.
      });
    },
    [accessCode, runId],
  );

  if (!accessCode) {
    return (
      <div className="mx-auto max-w-xl">
        <AccessGate
          onSubmit={(code) => {
            storeAccessCode(code);
            setAccessCode(code);
          }}
        />
      </div>
    );
  }

  if (status === "error") {
    return (
      <Banner tone="error">
        {error ?? "The run could not be loaded."}{" "}
        <Link to="/" className="text-accent underline underline-offset-4">
          Back to start
        </Link>
      </Banner>
    );
  }

  if (status === "loading") {
    return <LoadingState label="Loading run…" />;
  }

  if (report) {
    return (
      <div className="space-y-6">
        <header className="flex flex-wrap items-baseline justify-between gap-3">
          <h1 className="m-0 text-h2 font-semibold">Run {runId}</h1>
          <Link to="/" className="text-small text-accent underline underline-offset-4">
            New check
          </Link>
        </header>
        <ReviewSurface
          src={`${API_BASE}/runs/${runId}/artifacts/media/analysis.mp4`}
          data={toTimelineData(report)}
        />
        <DeviationPanel
          report={report}
          artifactUrl={(path) => `${API_BASE}/runs/${runId}/artifacts/${path}`}
          onDecide={decide}
          onExport={() =>
            window.open(
              `${API_BASE}/runs/${runId}/artifacts/report.html`,
              "_blank",
              "noopener",
            )
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="m-0 text-h2 font-semibold">Run {runId}</h1>
        <p className="mt-1 mb-0 text-muted">
          The run is processing. Findings appear here as soon as the report is ready.
        </p>
      </header>
      <RunProgress
        runId={runId}
        accessCode={accessCode}
        baseUrl={API_BASE}
        runHref={`/runs/${runId}`}
      />
    </div>
  );
}

/** Demo gallery: frozen offline cases (T-5.12). */
export function DemoPage() {
  const navigate = useNavigate();
  return <DemoGallery onOpen={(caseId) => navigate(`/demo/${caseId}`)} />;
}

export function NotFoundPage() {
  return (
    <EmptyState
      title="Not found"
      help="That page does not exist."
      action={
        <Link to="/" className="text-accent underline underline-offset-4">
          Back to start
        </Link>
      }
    />
  );
}
