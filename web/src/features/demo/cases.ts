import type { TimelineData } from "../review/timeline/data";

export type DemoDomain = "IT hardware" | "Laboratory" | "Mechanical";

export interface DemoCase {
  id: string;
  title: string;
  domain: DemoDomain;
  summary: string;
  /** Frozen, deterministic review data: no network, no model calls. */
  data: TimelineData;
}

function steps(count: number): { step_id: string; idx: number }[] {
  return Array.from({ length: count }, (_, index) => ({
    step_id: `stp_${String(index + 1).padStart(2, "0")}`,
    idx: index + 1,
  }));
}

function observed(
  windows: readonly [string | null, number, number][],
  startIndex: number,
): TimelineData["observed"] {
  return windows.map(([stepId, tStart, tEnd], offset) => ({
    interval_id: `int_${String(startIndex + offset).padStart(2, "0")}`,
    step_id: stepId,
    t_start: tStart,
    t_end: tEnd,
  }));
}

/**
 * The three frozen demo cases (FR-14, 05_Schema §12 `demo/cases`).
 *
 * Data is inline and deterministic so the gallery works with no backend at all; the
 * T-7.1 `pw demo-build` step replaces it with checksummed files under `demo/cases/`
 * using the same shape.
 */
export const DEMO_CASES: readonly DemoCase[] = [
  {
    id: "ssd-swap",
    title: "SSD swap: skipped power reconnect",
    domain: "IT hardware",
    summary: "A cable step is missed between the two drives; everything else is in order.",
    data: {
      duration_s: 118,
      expected: steps(10),
      observed: observed(
        [
          ["stp_01", 3.0, 12.4],
          ["stp_02", 13.0, 28.0],
          ["stp_03", 29.0, 40.0],
          [null, 40.0, 60.0],
          ["stp_05", 61.0, 71.0],
          ["stp_06", 72.0, 90.0],
          ["stp_07", 92.0, 104.0],
        ],
        1,
      ),
      deviations: [
        {
          id: "dev_001",
          type: "missed",
          status: "flagged",
          step_id: "stp_04",
          t_start: 61.0,
          t_end: 71.5,
        },
      ],
    },
  },
  {
    id: "standard-solution",
    title: "Standard solution: wrong tool for weighing",
    domain: "Laboratory",
    summary: "A kitchen scale is used where the SOP requires the analytical balance.",
    data: {
      duration_s: 132,
      expected: steps(9),
      observed: observed(
        [
          ["stp_01", 2.0, 10.0],
          ["stp_02", 18.0, 26.0],
          ["stp_03", 28.0, 40.0],
          ["stp_04", 42.0, 55.0],
          ["stp_05", 57.0, 70.0],
          ["stp_06", 72.0, 90.0],
          ["stp_07", 92.0, 105.0],
          ["stp_08", 107.0, 118.0],
          ["stp_09", 120.0, 130.0],
        ],
        1,
      ),
      deviations: [
        {
          id: "dev_001",
          type: "wrong_tool",
          status: "flagged",
          step_id: "stp_02",
          t_start: 18.0,
          t_end: 26.0,
        },
      ],
    },
  },
  {
    id: "cross-pattern-torque",
    title: "Cross-pattern torque: order slip and missing stripe",
    domain: "Mechanical",
    summary: "Two bolts are tightened out of order and the torque stripe is never applied.",
    data: {
      duration_s: 104,
      expected: steps(8),
      observed: observed(
        [
          ["stp_01", 2.0, 8.0],
          ["stp_02", 10.0, 20.0],
          ["stp_03", 22.0, 32.0],
          ["stp_04", 34.0, 44.0],
          ["stp_06", 54.0, 64.0],
          ["stp_05", 66.0, 74.0],
          ["stp_08", 86.0, 100.0],
        ],
        1,
      ),
      deviations: [
        {
          id: "dev_001",
          type: "out_of_order",
          status: "needs_review",
          step_id: "stp_05",
          t_start: 44.0,
          t_end: 52.0,
        },
        {
          id: "dev_002",
          type: "missed",
          status: "flagged",
          step_id: "stp_07",
          t_start: 76.0,
          t_end: 84.0,
        },
      ],
    },
  },
];
