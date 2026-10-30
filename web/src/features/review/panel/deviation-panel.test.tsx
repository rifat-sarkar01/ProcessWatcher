import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Deviation, Report } from "../../../types/generated/report";

import { DeviationPanel, type DeviationPanelProps } from "./deviation-panel";

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
    explanation: "Step 5 (bolt 2) was never torqued: the wrench moved straight on.",
    verifier: { ran: true, agreed: true },
    evidence: [
      {
        evidence_id: "evd_001",
        deviation_id: "dev_001",
        kind: "evidence",
        source_sha256: "a".repeat(64),
        frame_index: 1065,
        t: 71,
        render_version: "render-1.0.0",
        params_hash: "b".repeat(64),
        output_path: "evidence/evd_001.png",
        output_sha256: "c".repeat(64),
        phash: "f0e1d2c3b4a59687",
        track_ids: ["trk_001"],
        clip: {
          path: "evidence/evd_001.mp4",
          sha256: "d".repeat(64),
          t_start: 61,
          t_end: 71.5,
        },
      },
      {
        evidence_id: "evd_002",
        deviation_id: "dev_001",
        kind: "evidence",
        source_sha256: "a".repeat(64),
        frame_index: 1080,
        t: 72,
        render_version: "render-1.0.0",
        params_hash: "b".repeat(64),
        output_path: "evidence/evd_002.png",
        output_sha256: "e".repeat(64),
        phash: "a1b2c3d4e5f60718",
        track_ids: ["trk_001"],
      },
    ],
    evidence_unavailable: false,
    illustration: null,
    illustration_unavailable_reason: null,
    ...overrides,
  };
}

const REPORT: Report = {
  schema_version: "1.0.0",
  run_id: "run_1",
  created_at: "2026-10-27T09:15:47Z",
  status: "done",
  degraded_stages: [],
  sop: {
    schema_version: "1.0.0",
    sop_id: "sop_1",
    title: "4-bolt cross-pattern torque",
    source: { kind: "md", sha256: "f".repeat(64) },
    steps: Array.from({ length: 6 }, (_, index) => ({
      id: `stp_${String(index + 1).padStart(2, "0")}`,
      idx: index + 1,
      text: `Step ${index + 1}`,
      action: "tighten",
      tools: ["torque wrench"],
      parts: ["bolt"],
      ordering: "strict",
      group_id: null,
      critical: false,
      visual_check: null,
    })),
    vocabulary: { sam_concepts: ["hand"], zones: [] },
    warnings: [],
  },
  video: { sha256: "a".repeat(64), duration_s: 118, width: 1280, height: 720 },
  lanes: {
    expected: [{ step_id: "stp_01", idx: 1 }],
    observed: [{ interval_id: "int_01", step_id: "stp_01", t_start: 3, t_end: 12.4 }],
  },
  deviations: [
    deviation(),
    deviation({
      id: "dev_002",
      type: "wrong_tool",
      severity: "medium",
      step_id: "stp_04",
      t_start: 72.4,
      t_end: 81,
      confidence: 0.86,
      explanation: "Step 4 needs the torque wrench; an adjustable wrench was used.",
      expected_tools: ["torque wrench"],
      observed_tools: ["adjustable wrench"],
      evidence: [],
    }),
  ],
  summary: {
    flagged: 2,
    needs_review: 0,
    dropped: 1,
    by_type: { missed: 1, out_of_order: 0, wrong_tool: 1 },
  },
  manifest_ref: "manifest.json",
};

function renderPanel(overrides: Partial<DeviationPanelProps> = {}) {
  const props: DeviationPanelProps = {
    report: REPORT,
    artifactUrl: (path) => `/runs/run_1/artifacts/${path}`,
    ...overrides,
  };
  const view = render(<DeviationPanel {...props} />);
  return { ...view, props };
}

describe("DeviationPanel", () => {
  it("lists deviations in time order with type, severity, timecode and confidence", () => {
    const onSeek = vi.fn();
    renderPanel({ onSeek });

    const list = screen.getByRole("list", { name: "Deviations" });
    const cards = within(list).getAllByRole("listitem");
    expect(cards).toHaveLength(2);

    expect(within(cards[0]!).getByRole("heading", { name: "Step 5 skipped" })).toBeInTheDocument();
    expect(within(cards[0]!).getByText("Missed")).toBeInTheDocument();
    expect(within(cards[0]!).getByText("High")).toBeInTheDocument();
    expect(within(cards[0]!).getByRole("meter", { name: "Confidence" })).toHaveAttribute(
      "aria-valuenow",
      "82",
    );
    expect(within(cards[0]!).getByText(REPORT.deviations[0]!.explanation)).toBeInTheDocument();

    expect(
      within(cards[1]!).getByRole("heading", {
        name: "Wrong tool at step 4: torque wrench expected, adjustable wrench used",
      }),
    ).toBeInTheDocument();
    expect(within(cards[1]!).getByText("Wrong tool")).toBeInTheDocument();

    fireEvent.click(within(cards[0]!).getByRole("button", { name: "Seek to 01:01.0" }));
    expect(onSeek).toHaveBeenCalledWith(61);
  });

  it("gives every type chip an icon as well as a label", () => {
    renderPanel();

    const card = screen.getAllByRole("listitem")[0]!;
    const chip = within(card).getByText("Missed").closest("span");
    expect(chip?.querySelector("svg")).not.toBeNull();
    expect(chip?.textContent).toContain("Missed");
  });

  it("styles needs_review cards differently and says why", () => {
    renderPanel({
      report: {
        ...REPORT,
        deviations: [
          deviation({ id: "dev_003", status: "needs_review", confidence: 0.41, explanation: "Ambiguous." }),
        ],
        summary: { flagged: 0, needs_review: 1, dropped: 0, by_type: { missed: 1, out_of_order: 0, wrong_tool: 0 } },
      },
    });

    const card = screen.getByRole("listitem");
    expect(card.className).toContain("border-dashed");
    expect(card.className).toContain("border-needs-review");
    expect(screen.getByText("Needs review: the evidence is not conclusive.")).toBeInTheDocument();
    expect(screen.getByText("0 flagged · 1 needs review")).toBeInTheDocument();
  });

  it("steps through the evidence carousel and links the clip", () => {
    renderPanel();

    const carousel = screen.getByRole("group", { name: "Evidence carousel" });
    expect(within(carousel).getByText("Evidence 1 of 2")).toBeInTheDocument();

    const first = within(carousel).getByRole("img", {
      name: "Evidence frame at 01:11.0, step stp_05",
    });
    expect(first).toHaveAttribute("src", "/runs/run_1/artifacts/evidence/evd_001.png");
    expect(
      within(carousel).getByLabelText("Evidence clip from 01:01.0 to 01:11.5"),
    ).toBeInTheDocument();

    fireEvent.click(within(carousel).getByRole("button", { name: "Next evidence frame" }));
    expect(
      within(carousel).getByRole("img", { name: "Evidence frame at 01:12.0, step stp_05" }),
    ).toBeInTheDocument();
    expect(within(carousel).getByText("Evidence 2 of 2")).toBeInTheDocument();
    expect(within(carousel).getByRole("button", { name: "Next evidence frame" })).toBeDisabled();
    expect(within(carousel).getByRole("button", { name: "Previous evidence frame" })).toBeEnabled();
  });

  it("explains when evidence could not be extracted", () => {
    renderPanel({
      report: {
        ...REPORT,
        deviations: [
          deviation({
            id: "dev_004",
            evidence: [],
            evidence_unavailable: true,
            explanation: "Step 5 was missed.",
          }),
        ],
      },
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Evidence could not be extracted for this deviation.",
    );
    expect(screen.queryByRole("group", { name: "Evidence carousel" })).not.toBeInTheDocument();
  });

  it("marks illustrations as AI, never evidence", () => {
    renderPanel({
      report: {
        ...REPORT,
        deviations: [
          deviation({
            id: "dev_005",
            illustration: {
              id: "ill_001",
              kind: "illustration",
              path: "illustrations/ill_001.png",
              sha256: "9".repeat(64),
              watermark: true,
              qa: { verdict: "pass", attempts: 1 },
            },
          }),
        ],
      },
    });

    const figure = screen.getByRole("figure");
    expect(within(figure).getByText("AI ILLUSTRATION · NOT EVIDENCE")).toBeInTheDocument();
    expect(within(figure).getByRole("img", { name: "AI illustration, not evidence: Step 5 skipped" })).toHaveAttribute(
      "src",
      "/runs/run_1/artifacts/illustrations/ill_001.png",
    );
    expect(within(figure).getByText("What correct looks like (AI illustration, not evidence)")).toBeInTheDocument();
  });

  it("explains when an illustration was not produced", () => {
    renderPanel({
      report: {
        ...REPORT,
        deviations: [
          deviation({
            id: "dev_006",
            illustration: null,
            illustration_unavailable_reason: "Illustrations disabled for this run (PW_DISABLE_ILLUSTRATIONS).",
          }),
        ],
      },
    });

    expect(
      screen.getByText("Illustrations disabled for this run (PW_DISABLE_ILLUSTRATIONS)."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("figure")).not.toBeInTheDocument();
  });

  it("filters by type and reports an empty filter result", () => {
    renderPanel();

    const filters = screen.getByRole("group", { name: "Filter deviations" });
    fireEvent.click(within(filters).getByRole("button", { name: "Wrong tool" }));
    expect(within(filters).getByRole("button", { name: "Wrong tool" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(1);

    fireEvent.click(within(filters).getByRole("button", { name: "Out of order" }));
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.getByText("No deviations match this filter.")).toBeInTheDocument();
  });

  it("re-sorts by severity on demand", () => {
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "By severity" }));
    const cards = screen.getAllByRole("listitem");
    expect(within(cards[0]!).getByText("Missed")).toBeInTheDocument();
    expect(within(cards[1]!).getByText("Wrong tool")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "By severity" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("records accept, dismiss and note decisions", () => {
    const onDecide = vi.fn();
    const onNote = vi.fn();
    renderPanel({ onDecide, onNote });

    fireEvent.click(screen.getByRole("button", { name: "Accept dev_001" }));
    expect(onDecide).toHaveBeenCalledWith("dev_001", "accepted");
    expect(screen.getByTestId("decision-dev_001")).toHaveTextContent("Accepted");

    fireEvent.click(screen.getByRole("button", { name: "Dismiss dev_002" }));
    expect(onDecide).toHaveBeenCalledWith("dev_002", "dismissed");
    expect(screen.getByTestId("decision-dev_002")).toHaveTextContent("Dismissed");

    fireEvent.click(screen.getByRole("button", { name: "Add note dev_001" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Note for dev_001" }), {
      target: { value: "Check bolt 2 on the next run." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save note dev_001" }));

    expect(onNote).toHaveBeenCalledWith("dev_001", "Check bolt 2 on the next run.");
    expect(screen.getByTestId("deviation-note-dev_001")).toHaveTextContent(
      "Note: Check bolt 2 on the next run.",
    );
  });

  it("exports the report when the handler is provided", () => {
    const onExport = vi.fn();
    renderPanel({ onExport });

    fireEvent.click(screen.getByRole("button", { name: "Export report" }));
    expect(onExport).toHaveBeenCalledTimes(1);
  });

  it("hides the export button without a handler", () => {
    renderPanel();
    expect(screen.queryByRole("button", { name: "Export report" })).not.toBeInTheDocument();
  });

  it("shows the empty state only for a complete run", () => {
    renderPanel({
      report: {
        ...REPORT,
        deviations: [],
        summary: { flagged: 0, needs_review: 0, dropped: 0, by_type: { missed: 0, out_of_order: 0, wrong_tool: 0 } },
      },
    });

    expect(screen.getByRole("heading", { name: "No deviations found." })).toBeInTheDocument();
    expect(screen.getByText("Every step was observed in order.")).toBeInTheDocument();
  });

  it("explains a procedure that was not recognised", () => {
    renderPanel({
      report: { ...REPORT, status: "not_recognized", deviations: [] },
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "This video does not match the SOP closely enough to check it.",
    );
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "No deviations found." })).not.toBeInTheDocument();
  });

  it("banners degraded stages on a partial run", () => {
    renderPanel({
      report: { ...REPORT, status: "partial", degraded_stages: ["illustrate"] },
    });

    expect(screen.getByRole("status")).toHaveTextContent(
      "Some analysis was unavailable: Illustrations. Everything else is complete.",
    );
  });
});
