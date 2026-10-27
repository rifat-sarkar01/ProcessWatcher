import { describe, expect, it } from "vitest";

import {
  nextDeviation,
  previousDeviation,
  resolveKeyboardAction,
  type KeyboardDeviation,
} from "./keyboard";

const FPS = 15;

describe("resolveKeyboardAction", () => {
  it("rewinds one second on J", () => {
    expect(resolveKeyboardAction("j", FPS)).toEqual({ type: "seek-by", delta: -1 });
  });

  it("forwards one second on L", () => {
    expect(resolveKeyboardAction("l", FPS)).toEqual({ type: "seek-by", delta: 1 });
  });

  it("toggles playback on K", () => {
    expect(resolveKeyboardAction("k", FPS)).toEqual({ type: "toggle-play" });
  });

  it("accepts upper-case letters", () => {
    expect(resolveKeyboardAction("J", FPS)).toEqual({ type: "seek-by", delta: -1 });
  });

  it("steps one frame on arrow keys", () => {
    expect(resolveKeyboardAction("ArrowLeft", FPS)).toEqual({
      type: "seek-by",
      delta: -1 / FPS,
    });
    expect(resolveKeyboardAction("ArrowRight", FPS)).toEqual({
      type: "seek-by",
      delta: 1 / FPS,
    });
  });

  it("steps one second on shift+arrow", () => {
    expect(resolveKeyboardAction("ArrowRight", FPS, { shiftKey: true })).toEqual({
      type: "seek-by",
      delta: 1,
    });
    expect(resolveKeyboardAction("ArrowLeft", FPS, { shiftKey: true })).toEqual({
      type: "seek-by",
      delta: -1,
    });
  });

  it("jumps between deviations on N and P", () => {
    expect(resolveKeyboardAction("n", FPS)).toEqual({ type: "next-deviation" });
    expect(resolveKeyboardAction("p", FPS)).toEqual({ type: "previous-deviation" });
  });

  it("ignores unrelated keys", () => {
    expect(resolveKeyboardAction("x", FPS)).toBeNull();
    expect(resolveKeyboardAction("Enter", FPS)).toBeNull();
  });

  it("rejects a non-positive frame rate", () => {
    expect(() => resolveKeyboardAction("ArrowRight", 0)).toThrow(RangeError);
  });
});

function deviation(t_start: number, id = `dev_${t_start}`): KeyboardDeviation {
  return { id, t_start };
}

describe("nextDeviation", () => {
  it("returns the first deviation after the current time", () => {
    const list = [deviation(10), deviation(50), deviation(90)];

    expect(nextDeviation(list, 20)?.t_start).toBe(50);
  });

  it("returns null after the last deviation", () => {
    const list = [deviation(10), deviation(50)];

    expect(nextDeviation(list, 50)).toBeNull();
  });

  it("is order-independent", () => {
    const list = [deviation(90), deviation(10), deviation(50)];

    expect(nextDeviation(list, 0)?.t_start).toBe(10);
  });
});

describe("previousDeviation", () => {
  it("returns the last deviation before the current time", () => {
    const list = [deviation(10), deviation(50), deviation(90)];

    expect(previousDeviation(list, 60)?.t_start).toBe(50);
  });

  it("returns null before the first deviation", () => {
    const list = [deviation(10), deviation(50)];

    expect(previousDeviation(list, 10)).toBeNull();
  });
});
