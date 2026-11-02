/**
 * Upload flow types and pure step-graph helpers (FR-02, FR-11).
 *
 * The editor keeps step ids stable while `idx` follows the visual order — deleting or
 * reordering never renumbers ids (05_Schema §11 invariant 9). Validation mirrors the
 * SOP contract: 2–40 steps, non-empty text and unique ids.
 */

export type Ordering = "strict" | "unordered_group";

export interface StepDraft {
  id: string;
  idx: number;
  text: string;
  action: string;
  tools: string[];
  parts: string[];
  ordering: Ordering;
  group_id: string | null;
  critical: boolean;
  visual_check: string | null;
}

export interface StepGraph {
  schema_version: string;
  sop_id: string;
  title: string;
  source: { kind: string; sha256: string };
  steps: StepDraft[];
  vocabulary: { sam_concepts: string[] };
  warnings: string[];
}

export interface CompilePreview {
  step_graph: StepGraph;
  vocabulary: string[];
  warnings: string[];
}

export interface GraphIssue {
  code: string;
  message: string;
}

export const MIN_STEPS = 2;
export const MAX_STEPS = 40;

export function validateSteps(steps: StepDraft[]): GraphIssue[] {
  const issues: GraphIssue[] = [];
  if (steps.length < MIN_STEPS) {
    issues.push({
      code: "step_count",
      message: `A procedure needs at least ${MIN_STEPS} steps.`,
    });
  }
  if (steps.length > MAX_STEPS) {
    issues.push({
      code: "step_count",
      message: `A procedure can have at most ${MAX_STEPS} steps.`,
    });
  }
  const seen = new Set<string>();
  steps.forEach((step, index) => {
    if (!step.text.trim()) {
      issues.push({ code: "empty_text", message: `Step ${index + 1} needs text.` });
    }
    if (seen.has(step.id)) {
      issues.push({ code: "duplicate_id", message: `Step ${index + 1} reuses id ${step.id}.` });
    }
    seen.add(step.id);
    if (step.idx !== index + 1) {
      issues.push({
        code: "index_mismatch",
        message: `Step ${index + 1} is out of order.`,
      });
    }
  });
  return issues;
}

export function reindex(steps: StepDraft[]): StepDraft[] {
  return steps.map((step, index) => ({ ...step, idx: index + 1 }));
}

export function moveStep(steps: StepDraft[], index: number, delta: number): StepDraft[] {
  const target = index + delta;
  if (target < 0 || target >= steps.length) return steps;
  const next = [...steps];
  const [moved] = next.splice(index, 1);
  next.splice(target, 0, moved);
  return reindex(next);
}

/** Consecutive unordered steps share a group id; strict steps have none. */
export function normaliseGroups(steps: StepDraft[]): StepDraft[] {
  let group = 0;
  let previousUnordered = false;
  return steps.map((step) => {
    if (step.ordering !== "unordered_group") {
      previousUnordered = false;
      return { ...step, group_id: null };
    }
    if (!previousUnordered) group += 1;
    previousUnordered = true;
    return { ...step, group_id: `grp_${String(group).padStart(2, "0")}` };
  });
}

export function updateStep(
  steps: StepDraft[],
  index: number,
  patch: Partial<StepDraft>,
): StepDraft[] {
  return normaliseGroups(
    steps.map((step, position) => (position === index ? { ...step, ...patch } : step)),
  );
}

export function addTool(steps: StepDraft[], index: number, tool: string): StepDraft[] {
  const trimmed = tool.trim();
  if (!trimmed) return steps;
  return steps.map((step, position) =>
    position === index && !step.tools.includes(trimmed)
      ? { ...step, tools: [...step.tools, trimmed] }
      : step,
  );
}

export function removeTool(steps: StepDraft[], index: number, tool: string): StepDraft[] {
  return steps.map((step, position) =>
    position === index
      ? { ...step, tools: step.tools.filter((value) => value !== tool) }
      : step,
  );
}
