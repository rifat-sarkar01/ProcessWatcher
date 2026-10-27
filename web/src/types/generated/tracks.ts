/**
 * Generated from contracts/tracks.schema.json by web/scripts/gen-types.mjs — do not edit.
 * Contract: docs/05_Schema.md §15 (CI fails when this file is stale).
 */
export interface Track {
  id: string;
  concept: string;
  first_t: number;
  last_t: number;
  frames: Frame[];
  source_chunks?: string[];
}

export interface Frame {
  frame: number;
  t: number;
  box: number[];
  score: number;
  mask?: { encoding: string; data: string; };
  poly?: number[][];
}

export interface Tracks {
  schema_version: string;
  run_id: string;
  video: { sha256: string; duration_s: number; analysis_fps: number; width: number; height: number; frame_count: number; };
  tracks: Track[];
  stitching?: { fragmentation_ratio?: number; merges?: number; gaps_filled?: number; };
}
