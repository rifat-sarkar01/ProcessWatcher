import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { StepEditor } from "./step-editor";
import { STEPS } from "./test-fixtures";
import type { StepDraft } from "./types";

function Harness({ initial = STEPS }: { initial?: StepDraft[] }) {
  const [steps, setSteps] = useState(initial);
  return <StepEditor steps={steps} onChange={setSteps} />;
}

describe("StepEditor", () => {
  it("renders every step with accessible controls", () => {
    render(<StepEditor steps={STEPS} onChange={() => {}} />);

    expect(screen.getByLabelText("Step 1 text")).toHaveValue("Unplug the power cable.");
    expect(screen.getByLabelText("Step 2 text")).toHaveValue("Remove the cover.");
    expect(screen.getByLabelText("Step 1 critical")).toBeChecked();
    expect(screen.getByLabelText("Step 1 ordering")).toHaveValue("strict");
    expect(screen.getByRole("button", { name: "Remove hand from step 1" })).toBeInTheDocument();
  });

  it("moves a step and preserves ids while renumbering idx", () => {
    const onChange = vi.fn();
    render(<StepEditor steps={STEPS} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "Move step 1 down" }));

    const next = onChange.mock.calls[0][0] as typeof STEPS;
    expect(next.map((item) => item.id)).toEqual(["stp_02", "stp_01"]);
    expect(next.map((item) => item.idx)).toEqual([1, 2]);
    expect(next.map((item) => item.text)).toEqual([
      "Remove the cover.",
      "Unplug the power cable.",
    ]);
  });

  it("disables moving past the ends", () => {
    render(<StepEditor steps={STEPS} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: "Move step 1 up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move step 2 down" })).toBeDisabled();
  });

  it("blocks an empty step with an alert", () => {
    render(<Harness />);

    fireEvent.change(screen.getByLabelText("Step 2 text"), { target: { value: "   " } });

    expect(screen.getByRole("alert")).toHaveTextContent("Step 2 needs text.");
  });

  it("adds and removes tool chips", () => {
    render(<Harness />);

    fireEvent.change(screen.getByLabelText("New tool for step 1"), { target: { value: "cable" } });
    fireEvent.click(screen.getByRole("button", { name: "Add tool to step 1" }));
    expect(screen.getByRole("button", { name: "Remove cable from step 1" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove hand from step 1" }));
    expect(screen.queryByRole("button", { name: "Remove hand from step 1" })).toBeNull();
  });

  it("toggles critical and ordering, grouping adjacent any-order steps", () => {
    const onChange = vi.fn();
    render(<StepEditor steps={STEPS} onChange={onChange} />);

    fireEvent.click(screen.getByLabelText("Step 1 critical"));
    const afterCritical = onChange.mock.calls[0][0] as typeof STEPS;
    expect(afterCritical[0].critical).toBe(false);

    fireEvent.change(screen.getByLabelText("Step 1 ordering"), {
      target: { value: "unordered_group" },
    });
    const afterOrdering = onChange.mock.calls[1][0] as typeof STEPS;
    expect(afterOrdering[0].ordering).toBe("unordered_group");
    expect(afterOrdering[0].group_id).toBe("grp_01");
    expect(afterOrdering[1].group_id).toBeNull();
  });

  it("lists the current steps in document order", () => {
    render(<StepEditor steps={STEPS} onChange={() => {}} />);

    const first = screen.getByLabelText("Step 1 text");
    const second = screen.getByLabelText("Step 2 text");
    expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const items = screen.getAllByRole("listitem");
    expect(within(items[0]).getByLabelText("Step 1 text")).toBe(first);
  });
});
