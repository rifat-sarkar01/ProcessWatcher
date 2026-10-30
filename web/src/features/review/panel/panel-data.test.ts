import { describe, expect, it } from "vitest";

import type { Deviation } from "../../../types/generated/report";

import {
  confidencePercent,
  deviationTitle,
  filterDeviations,
  partialNotice,
  sortDeviations,
} from "./panel-data";

function deviation(overrides: Partial<Deviation> = {}): Deviation {
  return {
    id: "dev_001",
    type: "missed",
    status: "flagged",
    severity: "high",
    step_id: "stp_05",
    relates_to_step_id: null,
    t_start: 61,
    t_end: 71.5,
    track_ids: ["trk_001"],
    confidence: 0.82,
    margin: 2.4,
    explanation: "Step 5 (bolt 2) was never torqued.",
    verifier: { ran: true, agreed: true },
    evidence: [],
    evidence_unavailable: false,
    ...overrides,
  };
}

const DEVIATIONS = [
  deviation({ id: "dev_003", type: "wrong_tool", severity: "medium", t_start: 92 }),
  deviation({ id: "dev_001", type: "missed", severity: "high", t_start: 61 }),
  deviation({ id: "dev_002", type: "out_of_order", severity: "high", t_start: 72.4 }),
];

describe("sortDeviations", () => {
  it("sorts by time and breaks ties by id", () => {
    const sorted = sortDeviations(DEVIATIONS, "time");
    expect(sorted.map((item) => item.id)).toEqual(["dev_001", "dev_002", "dev_003"]);

    const tied = sortDeviations(
      [
        deviation({ id: "dev_010", t_start: 10 }),
        deviation({ id: "dev_009", t_start: 10 }),
      ],
      "time",
    );
    expect(tied.map((item) => item.id)).toEqual(["dev_009", "dev_010"]);
  });

  it("puts high severity first, then sorts by time", () => {
    const sorted = sortDeviations(DEVIATIONS, "severity");
    expect(sorted.map((item) => item.id)).toEqual(["dev_001", "dev_002", "dev_003"]);
  });

  it("does not mutate the input", () => {
    const copy = DEVIATIONS.map((item) => item.id);
    sortDeviations(DEVIATIONS, "severity");
    expect(DEVIATIONS.map((item) => item.id)).toEqual(copy);
  });
});

describe("filterDeviations", () => {
  it("keeps everything for the all filter", () => {
    expect(filterDeviations(DEVIATIONS, "all")).toHaveLength(3);
  });

  it("keeps only the selected type", () => {
    expect(filterDeviations(DEVIATIONS, "wrong_tool").map((item) => item.id)).toEqual(["dev_003"]);
  });
});

describe("confidencePercent", () => {
  it("rounds to whole percent and clamps to 0–100", () => {
    expect(confidencePercent(0.824)).toBe(82);
    expect(confidencePercent(1.4)).toBe(100);
    expect(confidencePercent(Number.NaN)).toBe(0);
  });
});

describe("deviationTitle", () => {
  it("names the missed step by its 1-based index", () => {
    expect(deviationTitle(deviation(), 5, null)).toBe("Step 5 skipped");
  });

  it("names both steps for an out-of-order deviation", () => {
    const item = deviation({ type: "out_of_order", step_id: "stp_05", relates_to_step_id: "stp_04" });
    expect(deviationTitle(item, 5, 4)).toBe("Step 5 done before step 4");
  });

  it("names expected and observed tools for a wrong-tool deviation", () => {
    const item = deviation({
      type: "wrong_tool",
      step_id: "stp_04",
      expected_tools: ["torque wrench"],
      observed_tools: ["adjustable wrench"],
    });
    expect(deviationTitle(item, 4, null)).toBe(
      "Wrong tool at step 4: torque wrench expected, adjustable wrench used",
    );
  });

  it("falls back to the step id when no index is known", () => {
    expect(deviationTitle(deviation({ type: "missed", step_id: "stp_07" }), null, null)).toBe(
      "Step stp_07 skipped",
    );
  });
});

describe("partialNotice", () => {
  it("names the degraded stages in the UI copy", () => {
    expect(partialNotice(["illustrate"])).toBe(
      "Some analysis was unavailable: Illustrations. Everything else is complete.",
    );
  });

  it("joins multiple stages", () => {
    expect(partialNotice(["illustrate", "verify"])).toBe(
      "Some analysis was unavailable: Illustrations, Verification. Everything else is complete.",
    );
  });

  it("returns an empty string when nothing degraded", () => {
    expect(partialNotice([])).toBe("");
  });
});
