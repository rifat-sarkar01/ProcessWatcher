import type { DemoCaseDetail as DemoCaseResponse, DemoCaseSummary } from "../../api";
import { toTimelineData, type TimelineData } from "../review/timeline/data";

export type DemoDomain = "IT hardware";

export interface DemoCase {
  id: string;
  title: string;
  domain: DemoDomain;
  description: string;
  duration_s: number;
  finding_count: number;
}

export interface DemoCaseDetail extends DemoCase {
  /** Frozen, deterministic review data: no network, no model calls. */
  data: TimelineData;
  media_path: string;
}

/** Every shipped demo case cleans a keyboard, so the domain is constant. */
export const DEMO_DOMAIN: DemoDomain = "IT hardware";

const CASE_NOTES: Record<string, string> = {
  "keyboard-missed-tilt":
    "Step 1 is correctly flagged; the flags on steps 6 and 7 are a known short-step limitation (see docs/results/failures.md).",
};

export function describeCase(caseId: string, description: string): string {
  const note = CASE_NOTES[caseId];
  return note ? `${description} ${note}` : description;
}

export function toDemoCase(summary: DemoCaseSummary): DemoCase {
  return {
    id: summary.case_id,
    title: summary.title,
    domain: DEMO_DOMAIN,
    description: describeCase(summary.case_id, summary.description),
    duration_s: summary.duration_s ?? 0,
    finding_count: summary.deviation_count ?? 0,
  };
}

export function toDemoCaseDetail(detail: DemoCaseResponse): DemoCaseDetail {
  return {
    ...toDemoCase(detail),
    data: toTimelineData(detail.report),
    media_path: detail.media.analysis,
  };
}
