import type { Deviation } from "../../../types/generated/report";
import type { DeviationType } from "../timeline/data";

export type ReviewDecision = "accepted" | "dismissed";
export type DecisionMap = Readonly<Record<string, ReviewDecision>>;
export type NoteMap = Readonly<Record<string, string>>;
export type DeviationFilter = "all" | DeviationType;
export type SortMode = "time" | "severity";

export const FILTERS: readonly { value: DeviationFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "missed", label: "Missed" },
  { value: "out_of_order", label: "Out of order" },
  { value: "wrong_tool", label: "Wrong tool" },
];

export const SEVERITY_LABEL: Record<Deviation["severity"], string> = {
  high: "High",
  medium: "Medium",
};

export const DECISION_LABEL: Record<ReviewDecision, string> = {
  accepted: "Accepted",
  dismissed: "Dismissed",
};

/** Type chip fill: the category colour at 16% alpha (03_UI_Spec §6). */
export const TYPE_CHIP_CLASS: Record<DeviationType, string> = {
  missed: "border-dev-missed bg-dev-missed/[0.16] text-dev-missed",
  out_of_order: "border-dev-order bg-dev-order/[0.16] text-dev-order",
  wrong_tool: "border-dev-tool bg-dev-tool/[0.16] text-dev-tool",
};

const SEVERITY_RANK: Record<Deviation["severity"], number> = { high: 0, medium: 1 };

const STAGE_LABEL: Record<string, string> = {
  illustrate: "Illustrations",
  verify: "Verification",
  evidence: "Evidence",
  score: "Scoring",
  align: "Alignment",
  deviations: "Deviations",
};

/** High severity first, then earliest time; "time" keeps the timeline order. */
export function sortDeviations(deviations: readonly Deviation[], mode: SortMode): Deviation[] {
  return [...deviations].sort((a, b) => {
    const severity = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
    if (mode === "severity" && severity !== 0) return severity;
    return a.t_start - b.t_start || a.id.localeCompare(b.id);
  });
}

export function filterDeviations(
  deviations: readonly Deviation[],
  filter: DeviationFilter,
): Deviation[] {
  return filter === "all" ? [...deviations] : deviations.filter((item) => item.type === filter);
}

export function confidencePercent(confidence: number): number {
  if (!Number.isFinite(confidence)) return 0;
  return Math.round(Math.min(Math.max(confidence, 0), 1) * 100);
}

/** Card heading in the wording from 03_UI_Spec §9. */
export function deviationTitle(
  deviation: Deviation,
  stepIdx: number | null,
  relatedIdx: number | null,
): string {
  const step = stepIdx ?? deviation.step_id;
  if (deviation.type === "missed") return `Step ${step} skipped`;
  if (deviation.type === "out_of_order") {
    const related = relatedIdx ?? deviation.relates_to_step_id ?? "an earlier step";
    return `Step ${step} done before step ${related}`;
  }
  const expected = deviation.expected_tools?.join(", ") || "the required tool";
  const observed = deviation.observed_tools?.join(", ") || "another tool";
  return `Wrong tool at step ${step}: ${expected} expected, ${observed} used`;
}

export function partialNotice(degradedStages: readonly string[]): string {
  if (degradedStages.length === 0) return "";
  const labels = degradedStages.map((stage) => STAGE_LABEL[stage] ?? stage);
  return `Some analysis was unavailable: ${labels.join(", ")}. Everything else is complete.`;
}
