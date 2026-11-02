import { expect, test } from "@playwright/test";

/**
 * G5 extra: the overlay draw budget measured in a real browser canvas.
 *
 * `web/src/features/review/overlay/perf.test.ts` times geometry against a stub context
 * (jsdom has no canvas). This spec runs the same 12-track/720p workload in Chromium and
 * forces a raster flush with `getImageData`, then asserts the 03_UI_Spec §7 budget:
 * p95 ≤ 8 ms.
 */
test("draws 12 tracks at 720p within the p95 budget", async ({ page }) => {
  await page.goto("/");

  const result = await page.evaluate(async () => {
    const { drawOverlay } = await import("/src/features/review/overlay/draw.ts");
    const { frameAt } = await import("/src/features/review/overlay/frames.ts");

    const SIZE = { width: 1280, height: 720 };
    const TRACK_COUNT = 12;
    const SEGMENTS = 12;

    function heavyTrack(index: number) {
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

    const tracks = Array.from({ length: TRACK_COUNT }, (_, index) => heavyTrack(index));
    const canvas = document.createElement("canvas");
    canvas.width = SIZE.width;
    canvas.height = SIZE.height;
    document.body.append(canvas);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas 2d context unavailable");

    const timings: number[] = [];
    const drawFrame = (index: number) => {
      const items = frameAt(tracks, (index % 90) / 15, 15);
      const started = performance.now();
      drawOverlay(ctx, items, SIZE);
      // Force Chromium to rasterise instead of only recording canvas commands.
      ctx.getImageData(0, 0, 1, 1);
      timings.push(performance.now() - started);
    };

    for (let index = 0; index < 30; index += 1) drawFrame(index);
    timings.length = 0;
    for (let index = 0; index < 200; index += 1) drawFrame(index);

    const sorted = [...timings].sort((left, right) => left - right);
    const percentile = (value: number) =>
      sorted[Math.min(sorted.length - 1, Math.ceil(value * sorted.length) - 1)] ?? 0;
    return {
      p50: percentile(0.5),
      p95: percentile(0.95),
      max: sorted[sorted.length - 1] ?? 0,
      samples: timings.length,
    };
  });

  console.log(
    `overlay p50=${result.p50.toFixed(2)}ms p95=${result.p95.toFixed(2)}ms ` +
      `max=${result.max.toFixed(2)}ms n=${result.samples}`,
  );
  expect(result.p95).toBeLessThanOrEqual(8);
});
