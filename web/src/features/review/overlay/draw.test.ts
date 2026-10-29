import { describe, expect, it } from "vitest";

import type { OverlayItem } from "./frames";
import { drawOverlay, hitTest, toPixels } from "./draw";

interface Call {
  name: string;
  args: unknown[];
}

function stubContext() {
  const calls: Call[] = [];
  const record =
    (name: string) =>
    (...args: unknown[]) => {
      calls.push({ name, args });
    };
  const ctx = {
    calls,
    save: record("save"),
    restore: record("restore"),
    beginPath: record("beginPath"),
    moveTo: record("moveTo"),
    lineTo: record("lineTo"),
    closePath: record("closePath"),
    fill: record("fill"),
    stroke: record("stroke"),
    fillRect: record("fillRect"),
    strokeRect: record("strokeRect"),
    clearRect: record("clearRect"),
    fillText: record("fillText"),
    measureText: () => ({ width: 40 }),
    set fillStyle(_value: string) {},
    set strokeStyle(_value: string) {},
    set lineWidth(_value: number) {},
    set font(_value: string) {},
    set globalAlpha(_value: number) {},
  };
  return ctx;
}

const ITEM: OverlayItem = {
  trackId: "trk_001",
  concept: "screwdriver",
  box: [0.1, 0.2, 0.3, 0.4],
  poly: [
    [0.1, 0.2],
    [0.3, 0.2],
    [0.3, 0.4],
    [0.1, 0.4],
  ],
  score: 0.9,
};

const SIZE = { width: 1280, height: 720 };

describe("toPixels", () => {
  it("scales normalised coordinates to the canvas", () => {
    expect(toPixels([0.5, 0.5], SIZE)).toEqual([640, 360]);
  });
});

describe("drawOverlay", () => {
  it("draws one polygon plus its label per item", () => {
    const ctx = stubContext();

    const drawn = drawOverlay(ctx as never, [ITEM], SIZE);

    expect(drawn).toBe(1);
    const names = ctx.calls.map((call) => call.name);
    expect(names).toContain("beginPath");
    expect(names).toContain("fill");
    expect(names).toContain("stroke");
    expect(names).toContain("fillText");
    expect(ctx.calls.filter((call) => call.name === "fillText")[0]?.args[0]).toBe(
      "#trk_001 screwdriver",
    );
  });

  it("falls back to the box when a sample has no polygon", () => {
    const ctx = stubContext();

    drawOverlay(ctx as never, [{ ...ITEM, poly: undefined }], SIZE);

    expect(ctx.calls.some((call) => call.name === "fillRect")).toBe(true);
    expect(ctx.calls.some((call) => call.name === "fillText")).toBe(true);
  });

  it("never draws when there are no items", () => {
    const ctx = stubContext();

    expect(drawOverlay(ctx as never, [], SIZE)).toBe(0);
    expect(ctx.calls).toEqual([]);
  });

  it("clears the previous frame first", () => {
    const ctx = { ...stubContext(), clearRect: () => undefined };
    const cleared: number[] = [];
    ctx.clearRect = (...args: number[]) => {
      cleared.push(args.length);
    };

    drawOverlay(ctx as never, [ITEM], SIZE);

    expect(cleared).toEqual([4]);
  });
});

describe("hitTest", () => {
  it("finds the track under a point inside its polygon", () => {
    expect(hitTest([ITEM], { width: 1280, height: 720 }, 0.2, 0.3)?.trackId).toBe("trk_001");
  });

  it("returns null outside every polygon", () => {
    expect(hitTest([ITEM], SIZE, 0.9, 0.9)).toBeNull();
  });

  it("respects the box bbox for box-only items", () => {
    const boxOnly = { ...ITEM, poly: undefined };

    expect(hitTest([boxOnly], SIZE, 0.2, 0.3)?.trackId).toBe("trk_001");
    expect(hitTest([boxOnly], SIZE, 0.5, 0.5)).toBeNull();
  });

  it("prefers the smallest containing shape when tracks overlap", () => {
    const big: OverlayItem = { ...ITEM, trackId: "trk_002", box: [0, 0, 1, 1], poly: undefined };

    expect(hitTest([big, ITEM], SIZE, 0.2, 0.3)?.trackId).toBe("trk_001");
  });
});
