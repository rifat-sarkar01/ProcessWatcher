/**
 * Processing screen (`02_AppFlow.md` §2.3, `03_UI_Spec.md` §6 StageStepper/CostMeter).
 *
 * One live region announces stage transitions politely; failures and the spend cap
 * are assertive banners. Stage events come from the T-5.4 SSE stream.
 */

import { formatTimecode } from "../review/timeline/format";
import type { ProgressState, StageState } from "./events";
import { useRunProgress, type StreamFetch } from "./use-run-progress";
import { Banner } from "../../ui/states";

const STATUS_TEXT: Record<StageState["status"], string> = {
  pending: "Waiting",
  running: "Running",
  done: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

function stageTone(status: StageState["status"]): string {
  switch (status) {
    case "done":
      return "text-ok";
    case "running":
      return "text-accent";
    case "failed":
      return "text-error";
    case "skipped":
      return "text-muted line-through";
    default:
      return "text-muted";
  }
}

function StageStepper({ state }: { state: ProgressState }) {
  return (
    <ol aria-label="Pipeline stages" className="m-0 flex list-none flex-wrap gap-2 p-0">
      {state.stages.map((stage) => {
        const isCurrent = stage.status === "running";
        return (
          <li
            key={stage.name}
            aria-current={isCurrent ? "step" : undefined}
            className={`flex min-h-11 min-w-40 flex-1 flex-col justify-center gap-1 rounded-control border px-3 py-2 ${
              isCurrent ? "border-accent bg-surface-2" : "border-border bg-surface"
            }`}
          >
            <span className="text-small text-muted">{stage.label}</span>
            <span className={`text-control font-medium ${stageTone(stage.status)}`}>
              {STATUS_TEXT[stage.status]}
              {stage.status === "running" ? ` ${Math.round(stage.pct)}%` : ""}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function announcement(state: ProgressState): string {
  if (state.runStatus === "done") return "Run complete.";
  const failed = state.stages.find((stage) => stage.name === state.failedStage);
  if (failed) return `Run stopped: stage ${failed.label} failed.`;
  const current = state.stages.find((stage) => stage.status === "running");
  if (current) {
    const index = state.stages.indexOf(current) + 1;
    return `Stage ${index} of ${state.stages.length}: ${current.label}.`;
  }
  if (state.connection === "retrying") return "Reconnecting to the progress stream.";
  return "Connecting to the progress stream.";
}

export interface RunProgressProps {
  runId: string;
  accessCode?: string | null;
  baseUrl?: string;
  fetchImpl?: StreamFetch;
  retryDelayMs?: number;
  initial?: ProgressState;
  spendCapUsd?: number;
  runHref?: string;
  onContinue?: (runId: string) => void;
}

export function RunProgress({
  runId,
  accessCode = null,
  baseUrl = "",
  fetchImpl,
  retryDelayMs,
  initial,
  spendCapUsd = 3,
  runHref,
  onContinue,
}: RunProgressProps) {
  const { state, error, retry } = useRunProgress({
    runId,
    accessCode,
    baseUrl,
    fetchImpl,
    retryDelayMs,
    initial,
  });

  const failed = state.stages.find((stage) => stage.name === state.failedStage);
  const atCap = spendCapUsd > 0 && state.costUsd + 1e-9 >= spendCapUsd;
  const nearCap = spendCapUsd > 0 && state.costUsd + 1e-9 >= spendCapUsd * 0.8;
  const costTone = atCap ? "text-error" : nearCap ? "text-dev-missed" : "text-fg";

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <p role="status" aria-live="polite" className="m-0 text-control text-muted">
          {announcement(state)}
        </p>
        <p className="m-0 flex items-baseline gap-4 font-mono text-small tabular-nums">
          <span data-testid="cost-meter" className={costTone}>
            ${state.costUsd.toFixed(2)} / ${spendCapUsd.toFixed(2)}
          </span>
          <span className="text-muted">{formatTimecode(state.elapsedS)}</span>
        </p>
      </div>

      <StageStepper state={state} />

      {state.previewReady && state.runStatus === "running" && runHref ? (
        <p className="m-0 text-small">
          <a href={runHref} className="text-accent underline underline-offset-4">
            Preview findings
          </a>
        </p>
      ) : null}

      {error ? (
        <Banner
          tone="error"
          action={
            <button
              type="button"
              className="min-h-11 rounded-control border border-border-strong px-4 text-control"
              onClick={retry}
            >
              Retry
            </button>
          }
        >
          {error}
        </Banner>
      ) : null}

      {failed ? (
        <Banner
          tone="error"
          action={
            onContinue ? (
              <button
                type="button"
                className="min-h-11 rounded-control border border-border-strong px-4 text-control"
                onClick={() => onContinue(runId)}
              >
                Continue with partial
              </button>
            ) : undefined
          }
        >
          Stage {failed.label} failed.{failed.reason ? ` ${failed.reason}` : ""}
        </Banner>
      ) : null}

      {atCap ? <Banner tone="error">Spend cap reached.</Banner> : null}
    </section>
  );
}
