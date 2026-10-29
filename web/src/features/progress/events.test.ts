import { describe, expect, it } from "vitest";

import {
  STAGE_LABELS,
  STAGE_NAMES,
  initialProgress,
  parseEvent,
  reduceProgress,
} from "./events";

const stage = (
  name: string,
  status: string,
  extra: { pct?: number; elapsed_s?: number; cost_usd?: number; reason?: string } = {},
) => ({
  event: "stage",
  data: JSON.stringify({
    stage: name,
    status,
    pct: extra.pct ?? 0,
    elapsed_s: extra.elapsed_s ?? 1,
    cost_usd: extra.cost_usd ?? 0,
    ...(extra.reason ? { reason: extra.reason } : {}),
  }),
});

describe("stage catalogue", () => {
  it("lists the 12 pipeline stages in DAG order", () => {
    expect(STAGE_NAMES).toHaveLength(12);
    expect(STAGE_NAMES[0]).toBe("ingest");
    expect(STAGE_NAMES.at(-1)).toBe("report");
    expect(STAGE_NAMES).toContain("deviations");
  });

  it("labels every stage for the stepper", () => {
    for (const name of STAGE_NAMES) {
      expect(STAGE_LABELS[name]).toMatch(/\S/);
    }
    expect(STAGE_LABELS.identify).toBe("Identify tools");
    expect(STAGE_LABELS.score).toBe("Score segments");
  });
});

describe("initialProgress", () => {
  it("starts every stage pending and connecting", () => {
    const state = initialProgress();

    expect(state.stages).toHaveLength(12);
    expect(state.stages.every((item) => item.status === "pending")).toBe(true);
    expect(state.connection).toBe("connecting");
    expect(state.runStatus).toBe("running");
    expect(state.costUsd).toBe(0);
    expect(state.previewReady).toBe(false);
    expect(state.failedStage).toBeNull();
  });
});

describe("parseEvent", () => {
  it("parses a stage event", () => {
    const event = parseEvent("stage", stage("ingest", "done", { pct: 100 }).data);

    expect(event).toEqual({
      kind: "stage",
      stage: "ingest",
      status: "done",
      pct: 100,
      elapsedS: 1,
      costUsd: 0,
      reason: null,
    });
  });

  it("parses done and heartbeat events", () => {
    expect(parseEvent("done", '{"status": "done"}')).toEqual({ kind: "done" });
    expect(parseEvent("heartbeat", '{"elapsed_s": 12.5}')).toEqual({
      kind: "heartbeat",
      elapsedS: 12.5,
    });
  });

  it("treats malformed or unknown events as no-ops", () => {
    expect(parseEvent("stage", "{not json")).toEqual({ kind: "unknown" });
    expect(parseEvent("mystery", "{}")).toEqual({ kind: "unknown" });
  });
});

describe("reduceProgress", () => {
  it("marks stages done in the order the stream reports them", () => {
    let state = initialProgress();
    state = reduceProgress(state, parseEvent("stage", stage("ingest", "done", { pct: 100 }).data));
    state = reduceProgress(
      state,
      parseEvent("stage", stage("sop_compile", "done", { pct: 100 }).data),
    );

    const statuses = state.stages.map((item) => item.status);
    expect(statuses.slice(0, 2)).toEqual(["done", "done"]);
    expect(statuses.slice(2).every((status) => status === "pending")).toBe(true);
    expect(state.connection).toBe("open");
  });

  it("is idempotent so a reconnect replay leaves the same state", () => {
    const replay = [
      parseEvent("stage", stage("ingest", "done", { pct: 100, elapsed_s: 2 }).data),
      parseEvent("stage", stage("sop_compile", "done", { pct: 100, elapsed_s: 3 }).data),
      parseEvent("stage", stage("perceive", "running", { pct: 40, elapsed_s: 4 }).data),
    ];

    const once = replay.reduce(reduceProgress, initialProgress());
    const twice = replay.reduce(reduceProgress, once);

    expect(twice).toEqual(once);
    expect(once.stages[2]).toMatchObject({ status: "running", pct: 40 });
  });

  it("keeps the highest cost and elapsed time across events", () => {
    let state = initialProgress();
    state = reduceProgress(
      state,
      parseEvent("stage", stage("ingest", "done", { cost_usd: 0.12, elapsed_s: 4 }).data),
    );
    state = reduceProgress(
      state,
      parseEvent("stage", stage("perceive", "running", { cost_usd: 0.08, elapsed_s: 2 }).data),
    );

    expect(state.costUsd).toBeCloseTo(0.12);
    expect(state.elapsedS).toBe(4);
  });

  it("surfaces a failed stage with its reason and never marks it done", () => {
    let state = initialProgress();
    state = reduceProgress(
      state,
      parseEvent("stage", stage("verify", "failed", { reason: "verifier timed out" }).data),
    );
    state = reduceProgress(state, parseEvent("stage", stage("verify", "done").data));

    expect(state.runStatus).toBe("failed");
    expect(state.failedStage).toBe("verify");
    const verify = state.stages.find((item) => item.name === "verify");
    expect(verify?.status).toBe("failed");
    expect(verify?.reason).toBe("verifier timed out");
  });

  it("offers the findings preview as soon as align completes", () => {
    let state = initialProgress();
    for (const name of ["ingest", "sop_compile", "perceive", "timeline", "identify", "score"]) {
      state = reduceProgress(state, parseEvent("stage", stage(name, "done", { pct: 100 }).data));
    }
    expect(state.previewReady).toBe(false);

    state = reduceProgress(state, parseEvent("stage", stage("align", "done", { pct: 100 }).data));
    expect(state.previewReady).toBe(true);
  });

  it("records a done run", () => {
    const state = reduceProgress(initialProgress(), parseEvent("done", '{"status": "done"}'));

    expect(state.runStatus).toBe("done");
  });

  it("keeps unknown stage names out of the stepper but still tracks cost", () => {
    const state = reduceProgress(
      initialProgress(),
      parseEvent("stage", stage("future_stage", "running", { cost_usd: 0.5 }).data),
    );

    expect(state.stages.every((item) => item.status === "pending")).toBe(true);
    expect(state.costUsd).toBeCloseTo(0.5);
  });

  it("marks skipped stages", () => {
    const state = reduceProgress(
      initialProgress(),
      parseEvent("stage", stage("illustrate", "skipped").data),
    );

    expect(state.stages.find((item) => item.name === "illustrate")?.status).toBe("skipped");
  });
});
