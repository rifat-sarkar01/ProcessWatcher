/**
 * Generated from contracts/sop.schema.json by web/scripts/gen-types.mjs — do not edit.
 * Contract: docs/05_Schema.md §15 (CI fails when this file is stale).
 */
export interface Step {
  id: string;
  idx: number;
  text: string;
  action: string;
  tools: string[];
  parts: string[];
  ordering: "strict" | "unordered_group";
  group_id?: string | null;
  critical: boolean;
  visual_check?: string | null;
}

export interface StepGraph {
  schema_version: string;
  sop_id: string;
  title: string;
  source: { kind: "md" | "txt" | "pdf" | "pasted"; sha256: string; pages?: number; };
  steps: Step[];
  vocabulary: { sam_concepts: string[]; zones?: string[]; };
  warnings?: string[];
}
