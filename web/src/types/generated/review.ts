/**
 * Generated from contracts/review.schema.json by web/scripts/gen-types.mjs — do not edit.
 * Contract: docs/05_Schema.md §15 (CI fails when this file is stale).
 */
export interface Review {
  schema_version: string;
  decisions: Array<{ deviation_id: string; decision: "accepted" | "dismissed"; note: string; decided_at: string; }>;
}
