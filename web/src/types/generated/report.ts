/**
 * Generated from contracts/report.schema.json by web/scripts/gen-types.mjs — do not edit.
 * Contract: docs/05_Schema.md §15 (CI fails when this file is stale).
 */
import type { StepGraph } from "./sop";

export interface Deviation {
  id: string;
  type: "missed" | "out_of_order" | "wrong_tool";
  status: "flagged" | "needs_review";
  severity: "high" | "medium";
  step_id: string;
  relates_to_step_id?: string | null;
  t_start: number;
  t_end: number;
  track_ids: string[];
  confidence: number;
  margin: number;
  explanation: string;
  verifier: Verifier;
  expected_tools?: string[];
  observed_tools?: string[];
  evidence: EvidenceItem[];
  evidence_unavailable: boolean;
  illustration?: Illustration | null;
  illustration_unavailable_reason?: string | null;
}

export interface Verifier {
  ran: boolean;
  agreed: boolean | null;
  note?: string;
}

export interface EvidenceItem {
  evidence_id: string;
  deviation_id: string;
  kind: "evidence";
  source_sha256: string;
  frame_index: number;
  t: number;
  render_version: string;
  params_hash: string;
  output_path: string;
  output_sha256: string;
  phash: string;
  track_ids: string[];
  clip?: { path: string; sha256: string; t_start: number; t_end: number; };
}

export interface Illustration {
  id: string;
  kind: "illustration";
  path?: string;
  sha256?: string;
  watermark: true;
  qa: { verdict: "pass" | "fail"; attempts: number; reason?: string; };
}

export interface Report {
  schema_version: string;
  run_id: string;
  created_at: string;
  status: "done" | "partial" | "not_recognized";
  degraded_stages: string[];
  sop: StepGraph;
  video: { sha256: string; duration_s: number; width: number; height: number; };
  lanes: { expected: { step_id: string; idx: number; }[]; observed: Array<{ interval_id: string; step_id: string | null; t_start: number; t_end: number; }>; };
  deviations: Deviation[];
  summary: { flagged: number; needs_review: number; dropped: number; by_type: { missed: number; out_of_order: number; wrong_tool: number; }; };
  manifest_ref: string;
  notice?: string;
}
