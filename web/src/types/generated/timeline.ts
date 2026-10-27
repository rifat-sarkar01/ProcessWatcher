/**
 * Generated from contracts/timeline.schema.json by web/scripts/gen-types.mjs — do not edit.
 * Contract: docs/05_Schema.md §15 (CI fails when this file is stale).
 */
export interface Event {
  id: string;
  type: "hold_start" | "hold_end" | "contact_start" | "contact_end" | "move" | "enter" | "exit";
  t_start: number;
  t_end: number;
  tracks: string[];
  confidence: number;
}

export interface Segment {
  id: string;
  t_start: number;
  t_end: number;
  salient_tracks: string[];
  event_ids: string[];
  kind: "activity" | "idle";
}

export interface Timeline {
  schema_version: string;
  run_id?: string;
  events: Event[];
  segments: Segment[];
}
