/**
 * Generated from contracts/thresholds.schema.json by web/scripts/gen-types.mjs — do not edit.
 * Contract: docs/05_Schema.md §15 (CI fails when this file is stale).
 */
export interface Thresholds {
  schema_version: string;
  analysis_fps: number;
  chunk: { seconds: number; overlap_seconds: number; };
  timeline: { contact_enter: number; contact_exit: number; enter_frames: number; exit_frames: number; min_hold_s: number; move_disp: number; idle_gap_s: number; seg_min_s: number; seg_max_s: number; };
  align: { eps: number; lambda_skip: number; lambda_skip_critical: number; lambda_back: number; tau_T: number; domain_coverage_min: number; domain_cost_max: number | null; };
  deviation: { tau_miss: number; tau_flag: number; tau_review: number; wrong_tool_conf: number; };
  limits: { max_duration_s: number; max_mb: number; spend_cap_usd: number; max_concurrent_runs: number; };
}
