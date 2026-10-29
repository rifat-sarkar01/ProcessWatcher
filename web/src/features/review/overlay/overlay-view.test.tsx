import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Track } from "../../../types/generated/tracks";

import type { Size } from "./draw";
import type { OverlayItem } from "./frames";
import { OverlayView } from "./overlay-view";

type DrawArgs = [CanvasRenderingContext2D, OverlayItem[], Size];
const spyDraw = (value = 1) =>
  vi.fn((...args: DrawArgs): number => {
    void args;
    return value;
  });

function track(id: string, concept: string, times: number[], score = 0.9): Track {
  return {
    id,
    concept,
    first_t: times[0] ?? 0,
    last_t: times.at(-1) ?? 0,
    frames: times.map((t, index) => ({
      frame: index,
      t,
      box: [0.1, 0.1, 0.4, 0.4],
      score,
      poly: [
        [0.1, 0.1],
        [0.4, 0.1],
        [0.4, 0.4],
        [0.1, 0.4],
      ],
    })),
  };
}

const TRACKS = [
  track("trk_001", "screwdriver", [0.0, 0.1, 0.2, 3.0]),
  track("trk_002", "hand", [0.0, 0.1, 0.2]),
];

const STUB_CONTEXT = {
  clearRect: () => undefined,
  beginPath: () => undefined,
  moveTo: () => undefined,
  lineTo: () => undefined,
  closePath: () => undefined,
  fill: () => undefined,
  stroke: () => undefined,
  fillRect: () => undefined,
  strokeRect: () => undefined,
  fillText: () => undefined,
  measureText: () => ({ width: 40 }),
  fillStyle: "",
  strokeStyle: "",
  lineWidth: 0,
  font: "",
  globalAlpha: 1,
} as unknown as CanvasRenderingContext2D;

const contextFor = () => STUB_CONTEXT;

function renderView(overrides: Partial<Parameters<typeof OverlayView>[0]> = {}) {
  const draw = spyDraw();
  render(
    <OverlayView
      tracks={TRACKS}
      currentTime={0.1}
      fps={15}
      draw={draw}
      contextFor={contextFor}
      {...overrides}
    />,
  );
  return { draw };
}

describe("OverlayView", () => {
  it("draws one item per visible track", () => {
    const { draw } = renderView();

    expect(draw).toHaveBeenCalled();
    const items = draw.mock.calls.at(-1)?.[1] as unknown[];
    expect(items).toHaveLength(2);
  });

  it("redraws when the playhead moves", () => {
    const draw = spyDraw(2);
    const { rerender } = render(
      <OverlayView
        tracks={TRACKS}
        currentTime={0.0}
        fps={15}
        draw={draw}
        contextFor={contextFor}
      />,
    );
    const before = draw.mock.calls.length;

    rerender(
      <OverlayView
        tracks={TRACKS}
        currentTime={0.2}
        fps={15}
        draw={draw}
        contextFor={contextFor}
      />,
    );

    expect(draw.mock.calls.length).toBeGreaterThan(before);
  });

  it("hides a whole concept when its chip is toggled off", () => {
    const { draw } = renderView();

    fireEvent.click(screen.getByRole("button", { name: /screwdriver/i }));

    const items = draw.mock.calls.at(-1)?.[1] as Array<{ concept: string }>;
    expect(items.map((item) => item.concept)).toEqual(["hand"]);
  });

  it("hides a single track from the inspector", () => {
    const { draw } = renderView();

    fireEvent.click(screen.getByRole("button", { name: /hide trk_001/i }));

    const items = draw.mock.calls.at(-1)?.[1] as Array<{ trackId: string }>;
    expect(items.map((item) => item.trackId)).toEqual(["trk_002"]);
  });

  it("shows the hovered id and concept", () => {
    renderView();
    const canvas = screen.getByTestId("overlay-canvas");
    canvas.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 1280, height: 720 }) as DOMRect;

    fireEvent.mouseMove(canvas, { clientX: 320, clientY: 200 });

    expect(screen.getByTestId("overlay-hover-label")).toHaveTextContent("#trk_001 screwdriver");
    fireEvent.mouseLeave(canvas);
    expect(screen.queryByTestId("overlay-hover-label")).not.toBeInTheDocument();
  });

  it("selects a track when the canvas is clicked", () => {
    const onSelectTrack = vi.fn();
    renderView({ onSelectTrack });
    const canvas = screen.getByTestId("overlay-canvas");
    canvas.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 1280, height: 720 }) as DOMRect;

    fireEvent.click(canvas, { clientX: 320, clientY: 200 });

    expect(onSelectTrack).toHaveBeenCalledWith("trk_001");
  });

  it("lists each track's holds in the inspector", () => {
    renderView();

    const row = screen.getByRole("listitem", { name: /trk_001/i });
    expect(row).toHaveTextContent("screwdriver");
    expect(row).toHaveTextContent("2 holds");
    expect(row).toHaveTextContent("00:00.0 – 00:00.2");
  });

  it("shows a confidence label per track", () => {
    renderView({ tracks: [track("trk_009", "bolt", [0, 0.1], 0.42)] });

    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("is a no-op with no tracks", () => {
    const draw = spyDraw(0);
    render(
      <OverlayView tracks={[]} currentTime={0} fps={15} draw={draw} contextFor={contextFor} />,
    );

    expect(screen.getByText(/no tracks/i)).toBeInTheDocument();
    expect(draw.mock.calls.at(-1)?.[1]).toEqual([]);
  });

  it("re-syncs off requestVideoFrameCallback when a video is supplied", () => {
    const draw = spyDraw();
    let callback: (() => void) | null = null;
    const video = {
      currentTime: 0.1,
      requestVideoFrameCallback: (next: () => void) => {
        callback = next;
        return 1;
      },
      cancelVideoFrameCallback: () => undefined,
    } as unknown as HTMLVideoElement;

    render(
      <OverlayView
        tracks={TRACKS}
        currentTime={0.1}
        fps={15}
        draw={draw}
        video={video}
        contextFor={contextFor}
      />,
    );
    const before = draw.mock.calls.length;
    (video as { currentTime: number }).currentTime = 3.0;
    act(() => {
      callback?.();
    });

    expect(draw.mock.calls.length).toBeGreaterThan(before);
    const items = draw.mock.calls.at(-1)?.[1] as Array<{ trackId: string }>;
    expect(items.map((item) => item.trackId)).toEqual(["trk_001"]);
  });
});
