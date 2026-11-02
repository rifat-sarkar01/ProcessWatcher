import type { CompilePreview, StepDraft } from "./types";

export function step(overrides: Partial<StepDraft> = {}): StepDraft {
  return {
    id: "stp_01",
    idx: 1,
    text: "Unplug the power cable.",
    action: "unplug",
    tools: ["hand"],
    parts: ["power cable"],
    ordering: "strict",
    group_id: null,
    critical: true,
    visual_check: null,
    ...overrides,
  };
}

export const STEPS: StepDraft[] = [
  step(),
  step({
    id: "stp_02",
    idx: 2,
    text: "Remove the cover.",
    action: "remove",
    tools: ["screwdriver"],
    parts: ["cover"],
    critical: false,
  }),
];

export const PREVIEW: CompilePreview = {
  step_graph: {
    schema_version: "1.0.0",
    sop_id: "sop_01234567",
    title: "Cable check",
    source: { kind: "md", sha256: "a".repeat(64) },
    steps: STEPS,
    vocabulary: { sam_concepts: ["hand", "screwdriver"] },
    warnings: [],
  },
  vocabulary: ["hand", "screwdriver"],
  warnings: [],
};
