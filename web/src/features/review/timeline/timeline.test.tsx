import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Timeline, type TimelineData } from "./timeline";

const DATA: TimelineData = {
  duration_s: 118,
  expected: [
    { step_id: "stp_01", idx: 1 },
    { step_id: "stp_02", idx: 2 },
    { step_id: "stp_03", idx: 3 },
    { step_id: "stp_04", idx: 4 },
    { step_id: "stp_05", idx: 5 },
    { step_id: "stp_06", idx: 6 },
  ],
  observed: [
    { interval_id: "int_01", step_id: "stp_01", t_start: 3.0, t_end: 12.4 },
    { interval_id: "int_02", step_id: null, t_start: 12.4, t_end: 28.6 },
    { interval_id: "int_03", step_id: "stp_02", t_start: 28.6, t_end: 41.0 },
  ],
  deviations: [
    {
      id: "dev_001",
      type: "missed",
      status: "flagged",
      step_id: "stp_05",
      t_start: 61.0,
      t_end: 71.5,
    },
    {
      id: "dev_002",
      type: "wrong_tool",
      status: "flagged",
      step_id: "stp_04",
      t_start: 72.4,
      t_end: 81.0,
    },
    {
      id: "dev_003",
      type: "out_of_order",
      status: "needs_review",
      step_id: "stp_06",
      t_start: 92.0,
      t_end: 95.5,
    },
  ],
};

function renderTimeline(currentTime = 0) {
  const onSeek = vi.fn();
  const view = render(<Timeline data={DATA} currentTime={currentTime} onSeek={onSeek} />);
  return { ...view, onSeek };
}

describe("Timeline", () => {
  it("renders the expected and observed lanes", () => {
    renderTimeline();

    expect(screen.getByRole("group", { name: "Expected steps" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Observed segments" })).toBeInTheDocument();
    expect(screen.getAllByText("stp_01").length).toBeGreaterThan(0);
    expect(screen.getByText("stp_06")).toBeInTheDocument();
  });

  it("renders one marker per deviation", () => {
    renderTimeline();

    expect(screen.getAllByTestId("deviation-marker")).toHaveLength(3);
  });

  it("places three deviations at their expected x positions", () => {
    renderTimeline();

    const markers = screen.getAllByTestId("deviation-marker");
    const left = (index: number) => parseFloat(markers[index]!.style.left);

    expect(left(0)).toBeCloseTo((61.0 / 118) * 100, 3);
    expect(left(1)).toBeCloseTo((72.4 / 118) * 100, 3);
    expect(left(2)).toBeCloseTo((92.0 / 118) * 100, 3);
  });

  it("seeks to the deviation start when a marker is clicked", () => {
    const { onSeek } = renderTimeline();

    fireEvent.click(screen.getByRole("button", { name: /Wrong tool step stp_04/ }));

    expect(onSeek).toHaveBeenCalledWith(72.4);
  });

  it("labels markers with type, step and timecode", () => {
    renderTimeline();

    expect(
      screen.getByRole("button", { name: "Missed step stp_05 at 01:01.0" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Wrong tool step stp_04 at 01:12.4" }),
    ).toBeInTheDocument();
  });

  it("marks needs_review deviations as dashed and announces them", () => {
    renderTimeline();

    const marker = screen.getByRole("button", { name: /Out of order step stp_06/ });
    expect(marker).toHaveAttribute("data-status", "needs_review");
    expect(marker.className).toContain("border-dashed");
    expect(marker.getAttribute("aria-label")).toContain("needs review");
  });

  it("colours markers by deviation type", () => {
    renderTimeline();

    const markers = screen.getAllByTestId("deviation-marker");
    expect(markers[0]!.className).toContain("text-dev-missed");
    expect(markers[1]!.className).toContain("text-dev-tool");
    expect(markers[2]!.className).toContain("text-dev-order");
  });

  it("positions the playhead from currentTime", () => {
    renderTimeline(59);

    const playhead = screen.getByTestId("playhead");
    expect(parseFloat(playhead.style.left)).toBeCloseTo(50, 3);
  });

  it("renders an empty lane when there are no observed intervals", () => {
    const onSeek = vi.fn();
    render(
      <Timeline
        data={{ ...DATA, observed: [], deviations: [] }}
        currentTime={0}
        onSeek={onSeek}
      />,
    );

    const observed = screen.getByRole("group", { name: "Observed segments" });
    expect(within(observed).queryByTestId("observed-block")).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("deviation-marker")).toHaveLength(0);
  });
});
