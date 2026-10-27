/**
 * Generated from contracts/manifest.schema.json by web/scripts/gen-types.mjs — do not edit.
 * Contract: docs/05_Schema.md §15 (CI fails when this file is stale).
 */
export interface Manifest {
  schema_version: string;
  run_id: string;
  created_at: string;
  finished_at: string;
  mode: "live" | "replay" | "fake" | "demo";
  inputs: { video_sha256: string; sop_sha256: string; step_graph_sha256: string; edited_by_user: boolean; };
  models: Array<{ name: "muse-wonder-1.0" | "muse-image-1.0" | "sam-3.1"; version_or_date: string; endpoint: string; }>;
  config_sha256: string;
  stages: Array<{ stage: string; status: "ok" | "failed" | "skipped"; started_at: string; duration_ms: number; cache_hit: boolean; cost_usd: number; }>;
  ledger: { total_usd: number; by_model: Record<string, number>; calls: number; cache_hits: number; spend_cap_usd: number; cap_reached: boolean; };
  dropped_candidates: number;
  git_commit: string;
  app_version: string;
}
