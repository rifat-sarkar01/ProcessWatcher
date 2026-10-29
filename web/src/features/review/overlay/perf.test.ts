/**
 * Overlay draw budget (03_UI_Spec §7: p95 ≤ 8 ms with 12 tracks at 720p).
 *
 * jsdom has no canvas, so the measurement uses a recording stub context: it times the
 * geometry work the overlay owns (polygon simplification, path building, labels), not
 * GPU rasterisation. Run with `npm --prefix web run test:perf -- --run`.
 */

import { describe, expect, it } from "vitest";

import type { Track } from "../../../types/generated/tracks";

import { drawOverlay } from "./draw";
import { frameAt } from "./frames";

const SIZE = { width: 1280, height: 720 };
const TRACK_COUNT = 12;
const SEGMENTS = 12;

function heavyTrack(index: number): Track {
  const frames = Array.from({ length: 90 }, (_, frame) => {
    const base = 0.1 + (index % 4) * 0.1;
    const poly = Array.from({ length: SEGMENTS }, (__, point) => {
      const angle = (point / SEGMENTS) * Math.PI * 2;
      return [
        base + 0.08 * Math.cos(angle) + frame * 0.0005,
        base + 0.08 * Math.sin(angle),
      ];
    });
    return {
      frame,
      t: frame / 15,
      box: [base, base, base + 0.16, base + 0.16],
      score: 0.9,
      poly,
    };
  });
  return {
    id: `trk_${String(index + 1).padStart(3, "0")}`,
    concept: index % 2 === 0 ? "hand" : "screwdriver",
    first_t: 0,
    last_t: 6,
    frames,
  };
}

const TRACKS = Array.from({ length: TRACK_COUNT }, (_, index) => heavyTrack(index));

function stubContext() {
  const noop = () => undefined;
  return {
    save: noop,
    restore: noop,
    beginPath: noop,
    moveTo: noop,
    lineTo: noop,
    closePath: noop,
    fill: noop,
    stroke: noop,
    fillRect: noop,
    strokeRect: noop,
    fillText: noop,
    clearRect: noop,
    measureText: () => ({ width: 40 }),
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 0,
    font: "",
    globalAlpha: 1,
  };
}

function percentile(values: number[], p: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[index] ?? 0;
}

describe("overlay draw budget", () => {
  it("draws 12 tracks at 720p within the p95 budget", () => {
    const ctx = stubContext();
    const timings: number[] = [];

    for (let run = 0; run < 60; run += 1) {
      const items = frameAt(TRACKS, run / 10, 15);
      expect(items).toHaveLength(TRACK_COUNT);
      const started = performance.now();
      drawOverlay(ctx as never, items, SIZE);
      timings.push(performance.now() - started);
    }

    const p95 = percentile(timings, 95);
    expect(p95).toBeLessThanOrEqual(8);
  });

  it("keeps frame lookup cheap as the playhead sweeps", () => {
    const timings: number[] = [];

    for (let run = 0; run < 200; run += 1) {
      const started = performance.now();
      frameAt(TRACKS, (run % 90) / 15, 15);
      timings.push(performance.now() - started);
    }

    expect(percentile(timings, 95)).toBeLessThanOrEqual(2);
  });
});
