import { describe, expect, it } from "vitest";

import { createTimeScale, timeToPercent } from "./scale";

describe("createTimeScale", () => {
  it("maps the start of the clip to the left edge", () => {
    const scale = createTimeScale(100, 800);

    expect(scale.timeToX(0)).toBe(0);
  });

  it("maps the end of the clip to the right edge", () => {
    const scale = createTimeScale(100, 800);

    expect(scale.timeToX(100)).toBe(800);
  });

  it("maps a mid-point proportionally", () => {
    const scale = createTimeScale(100, 800);

    expect(scale.timeToX(25)).toBeCloseTo(200, 6);
  });

  it("round-trips through xToTime", () => {
    const scale = createTimeScale(118, 900);

    expect(scale.xToTime(scale.timeToX(72.4))).toBeCloseTo(72.4, 6);
  });

  it("clamps times outside the clip", () => {
    const scale = createTimeScale(100, 800);

    expect(scale.timeToX(-5)).toBe(0);
    expect(scale.timeToX(150)).toBe(800);
    expect(scale.xToTime(-20)).toBe(0);
    expect(scale.xToTime(900)).toBe(100);
  });

  it("supports horizontal padding", () => {
    const scale = createTimeScale(10, 110, { padding: 5 });

    expect(scale.timeToX(0)).toBe(5);
    expect(scale.timeToX(10)).toBe(105);
    expect(scale.timeToX(5)).toBeCloseTo(55, 6);
  });

  it("rejects a zero or negative duration", () => {
    expect(() => createTimeScale(0, 800)).toThrow(RangeError);
    expect(() => createTimeScale(-1, 800)).toThrow(RangeError);
  });

  it("rejects a width that is too small for the padding", () => {
    expect(() => createTimeScale(10, 8, { padding: 5 })).toThrow(RangeError);
  });
});

describe("timeToPercent", () => {
  it("converts seconds to a 0–100 percentage", () => {
    expect(timeToPercent(0, 118)).toBe(0);
    expect(timeToPercent(59, 118)).toBe(50);
    expect(timeToPercent(118, 118)).toBe(100);
  });

  it("clamps outside the clip", () => {
    expect(timeToPercent(-3, 118)).toBe(0);
    expect(timeToPercent(500, 118)).toBe(100);
  });

  it("returns 0 for a non-positive duration instead of dividing by zero", () => {
    expect(timeToPercent(10, 0)).toBe(0);
  });
});
