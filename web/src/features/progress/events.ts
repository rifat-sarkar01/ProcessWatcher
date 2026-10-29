/**
 * Progress model for a running pipeline (`02_AppFlow.md` §2.3).
 *
 * The SSE stream is the only input: `stage` events tick the stepper, `done` closes the
 * run. Reducing is idempotent so a reconnect replay (T-5.4 re-emits every finished
 * stage) never duplicates work or regresses a stage.
 */

export const STAGE_NAMES = [
  "ingest",
  "sop_compile",
  "perceive",
  "timeline",
  "identify",
  "score",
  "align",
  "deviations",
  "verify",
  "evidence",
  "illustrate",
  "report",
] as const;

export type StageName = (typeof STAGE_NAMES)[number];

export const STAGE_LABELS: Record<StageName, string> = {
  ingest: "Ingest",
  sop_compile: "Compile SOP",
  perceive: "Perceive",
  timeline: "Timeline",
  identify: "Identify tools",
  score: "Score segments",
  align: "Align",
  deviations: "Deviations",
  verify: "Verify",
  evidence: "Evidence",
  illustrate: "Illustrate",
  report: "Report",
};

export type StageStatus = "pending" | "running" | "done" | "failed" | "skipped";

const STAGE_STATUSES: readonly StageStatus[] = [
  "pending",
  "running",
  "done",
  "failed",
  "skipped",
];

export type Connection = "connecting" | "open" | "retrying" | "closed";

export interface StageState {
  name: StageName;
  label: string;
  status: StageStatus;
  pct: number;
  elapsedS: number;
  reason: string | null;
}

export interface ProgressState {
  stages: StageState[];
  connection: Connection;
  runStatus: "running" | "done" | "failed";
  costUsd: number;
  elapsedS: number;
  failedStage: StageName | null;
  previewReady: boolean;
}

export type ProgressEvent =
  | {
      kind: "stage";
      stage: string;
      status: StageStatus;
      pct: number;
      elapsedS: number;
      costUsd: number;
      reason: string | null;
    }
  | { kind: "done" }
  | { kind: "heartbeat"; elapsedS: number }
  | { kind: "unknown" };

export function initialProgress(): ProgressState {
  return {
    stages: STAGE_NAMES.map((name) => ({
      name,
      label: STAGE_LABELS[name],
      status: "pending",
      pct: 0,
      elapsedS: 0,
      reason: null,
    })),
    connection: "connecting",
    runStatus: "running",
    costUsd: 0,
    elapsedS: 0,
    failedStage: null,
    previewReady: false,
  };
}

function isStageName(value: string): value is StageName {
  return (STAGE_NAMES as readonly string[]).includes(value);
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Turn one SSE frame into a typed event; anything unreadable becomes `unknown`. */
export function parseEvent(eventName: string, data: string): ProgressEvent {
  if (eventName === "done") return { kind: "done" };

  let payload: unknown;
  try {
    payload = JSON.parse(data) as unknown;
  } catch {
    return { kind: "unknown" };
  }
  if (!payload || typeof payload !== "object") return { kind: "unknown" };
  const record = payload as Record<string, unknown>;

  if (eventName === "heartbeat") {
    return { kind: "heartbeat", elapsedS: asNumber(record.elapsed_s) };
  }
  if (eventName !== "stage") return { kind: "unknown" };

  const stage = asString(record.stage);
  if (!stage) return { kind: "unknown" };
  const rawStatus = asString(record.status) ?? "running";
  const status = (STAGE_STATUSES as readonly string[]).includes(rawStatus)
    ? (rawStatus as StageStatus)
    : "running";

  return {
    kind: "stage",
    stage,
    status,
    pct: Math.min(100, Math.max(0, asNumber(record.pct))),
    elapsedS: asNumber(record.elapsed_s),
    costUsd: asNumber(record.cost_usd),
    reason: asString(record.reason),
  };
}

export function reduceProgress(state: ProgressState, event: ProgressEvent): ProgressState {
  switch (event.kind) {
    case "done":
      return { ...state, runStatus: "done", connection: "open" };
    case "heartbeat":
      return {
        ...state,
        connection: "open",
        elapsedS: Math.max(state.elapsedS, event.elapsedS),
      };
    case "unknown":
      return state;
    case "stage":
      break;
  }

  const costUsd = Math.max(state.costUsd, event.costUsd);
  const elapsedS = Math.max(state.elapsedS, event.elapsedS);

  if (!isStageName(event.stage)) {
    return { ...state, connection: "open", costUsd, elapsedS };
  }

  let changed = false;
  const stages = state.stages.map((item) => {
    if (item.name !== event.stage) return item;
    // A failure is final for the stepper: a late replay must not turn it green.
    if (item.status === "failed" && event.status !== "failed") return item;
    changed = true;
    return {
      ...item,
      status: event.status,
      pct: event.status === "done" ? 100 : event.pct,
      elapsedS: Math.max(item.elapsedS, event.elapsedS),
      reason: event.reason ?? item.reason,
    };
  });

  const failed = event.status === "failed" ? event.stage : state.failedStage;
  return {
    ...state,
    stages: changed ? stages : state.stages,
    connection: "open",
    runStatus: failed ? "failed" : state.runStatus,
    costUsd,
    elapsedS,
    failedStage: failed,
    previewReady: state.previewReady || (event.stage === "align" && event.status === "done"),
  };
}
