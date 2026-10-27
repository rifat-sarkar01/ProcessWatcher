import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TimelineData } from "../timeline/timeline";
import { ReviewSurface } from "./review-surface";

const DATA: TimelineData = {
  duration_s: 118,
  expected: [{ step_id: "stp_01", idx: 1 }],
  observed: [{ interval_id: "int_01", step_id: "stp_01", t_start: 3, t_end: 12.4 }],
  deviations: [
    { id: "dev_001", type: "missed", status: "flagged", step_id: "stp_05", t_start: 61, t_end: 71.5 },
    { id: "dev_002", type: "wrong_tool", status: "flagged", step_id: "stp_04", t_start: 72.4, t_end: 81 },
    { id: "dev_003", type: "out_of_order", status: "needs_review", step_id: "stp_06", t_start: 92, t_end: 95.5 },
  ],
};

function renderSurface() {
  return render(<ReviewSurface src="/runs/run_1/analysis.mp4" data={DATA} fps={15} />);
}

function timecode(): string {
  return screen.getByTestId("current-time").textContent ?? "";
}

describe("ReviewSurface", () => {
  beforeEach(() => {
    vi.spyOn(window.HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the video, transport and the dual-lane timeline", () => {
    renderSurface();

    expect(screen.getByTestId("review-video")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Expected steps" })).toBeInTheDocument();
    expect(timecode()).toBe("00:00.0");
  });

  it("jumps to the next deviation with N and the next one after that", () => {
    renderSurface();

    fireEvent.keyDown(window, { key: "n" });
    expect(timecode()).toBe("01:01.0");

    fireEvent.keyDown(window, { key: "n" });
    expect(timecode()).toBe("01:12.4");
  });

  it("jumps back to the previous deviation with P", () => {
    renderSurface();

    fireEvent.keyDown(window, { key: "n" });
    fireEvent.keyDown(window, { key: "n" });
    fireEvent.keyDown(window, { key: "p" });

    expect(timecode()).toBe("01:01.0");
  });

  it("steps one second with shift+arrow", () => {
    renderSurface();

    fireEvent.keyDown(window, { key: "ArrowRight", shiftKey: true });

    expect(timecode()).toBe("00:01.0");
  });

  it("scrubs one second forward and back with L and J", () => {
    renderSurface();

    fireEvent.keyDown(window, { key: "l" });
    expect(timecode()).toBe("00:01.0");

    fireEvent.keyDown(window, { key: "j" });
    expect(timecode()).toBe("00:00.0");
  });

  it("never seeks before the start of the clip", () => {
    renderSurface();

    fireEvent.keyDown(window, { key: "j" });
    fireEvent.keyDown(window, { key: "p" });

    expect(timecode()).toBe("00:00.0");
  });

  it("toggles playback with K", () => {
    renderSurface();

    fireEvent.keyDown(window, { key: "k" });
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "k" });
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("seeks to a deviation when its marker is clicked", () => {
    renderSurface();

    fireEvent.click(screen.getByRole("button", { name: /Wrong tool step stp_04/ }));

    expect(timecode()).toBe("01:12.4");
  });

  it("keeps the playhead and the timecode in sync", () => {
    renderSurface();

    fireEvent.keyDown(window, { key: "n" });

    const playhead = screen.getByTestId("playhead");
    expect(parseFloat(playhead.style.left)).toBeCloseTo((61 / 118) * 100, 3);
  });
});
