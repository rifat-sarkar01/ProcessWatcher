/**
 * Generated from contracts/alignment.schema.json by web/scripts/gen-types.mjs — do not edit.
 * Contract: docs/05_Schema.md §15 (CI fails when this file is stale).
 */
export interface IdentitiesFile {
  schema_version: string;
  run_id?: string;
  identities: Identity[];
}

export interface Identity {
  track_id: string;
  label: string;
  confidence: number;
  votes: { label: string; count: number; }[];
  crop_frames?: number[];
}

export interface LikelihoodsFile {
  schema_version: string;
  run_id?: string;
  segments: LikelihoodSegment[];
}

export interface LikelihoodSegment {
  segment_id: string;
  step_probs: Record<string, number>;
  observed_tools: { track: string; label: string; confidence: number; }[];
  rationale_short: string;
  flags: string[];
}

export interface AlignmentFile {
  schema_version: string;
  run_id?: string;
  path: { segment_id: string; step_id: string; }[];
  intervals: Interval[];
  cost: { total: number; per_segment: number; coverage: number; };
  params: Record<string, number | null>;
  status: "ok" | "procedure_not_recognized";
}

export interface Interval {
  id: string;
  step_id: string;
  t_start: number;
  t_end: number;
  segment_ids: string[];
  mean_prob: number;
  margin: number;
}

export type AlignmentArtifacts = IdentitiesFile | LikelihoodsFile | AlignmentFile;
