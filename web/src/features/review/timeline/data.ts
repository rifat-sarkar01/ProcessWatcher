import type { Report } from "../../../types/generated/report";

import { formatTimecode } from "./format";

export type DeviationType = "missed" | "out_of_order" | "wrong_tool";
export type DeviationStatus = "flagged" | "needs_review";

export interface TimelineDeviation {
  id: string;
  type: DeviationType;
  status: DeviationStatus;
  step_id: string;
  t_start: number;
  t_end: number;
}

export interface ExpectedStep {
  step_id: string;
  idx: number;
}

export interface ObservedInterval {
  interval_id: string;
  step_id: string | null;
  t_start: number;
  t_end: number;
}

export interface TimelineData {
  duration_s: number;
  expected: ExpectedStep[];
  observed: ObservedInterval[];
  deviations: TimelineDeviation[];
}

/** Label prefix per deviation type (03_UI_Spec §2: colour is never the only signal). */
export const TYPE_LABEL: Record<DeviationType, string> = {
  missed: "Missed",
  out_of_order: "Out of order",
  wrong_tool: "Wrong tool",
};

/** Token-backed classes per deviation type; no raw hex in components. */
export const TYPE_CLASS: Record<DeviationType, string> = {
  missed: "text-dev-missed border-dev-missed",
  out_of_order: "text-dev-order border-dev-order",
  wrong_tool: "text-dev-tool border-dev-tool",
};

/** Adapt a contract `report.json` into the shape the lanes need. */
export function toTimelineData(report: Report): TimelineData {
  return {
    duration_s: report.video.duration_s,
    expected: report.lanes.expected.map((step) => ({ step_id: step.step_id, idx: step.idx })),
    observed: report.lanes.observed.map((interval) => ({
      interval_id: interval.interval_id,
      step_id: interval.step_id,
      t_start: interval.t_start,
      t_end: interval.t_end,
    })),
    deviations: report.deviations.map((deviation) => ({
      id: deviation.id,
      type: deviation.type,
      status: deviation.status,
      step_id: deviation.step_id,
      t_start: deviation.t_start,
      t_end: deviation.t_end,
    })),
  };
}

/** Accessible marker label, e.g. "Wrong tool step stp_04 at 01:12.4 (needs review)". */
export function deviationLabel(deviation: TimelineDeviation): string {
  const base = `${TYPE_LABEL[deviation.type]} step ${deviation.step_id} at ${formatTimecode(deviation.t_start)}`;
  return deviation.status === "needs_review" ? `${base} (needs review)` : base;
}
