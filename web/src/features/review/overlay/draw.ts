/**
 * Canvas painting for the SAM overlay (03_UI_Spec §7).
 *
 * Draw order per frame: mask → outline → label chip → timestamp burn-in (evidence only,
 * T-4.x). Colours come from the spec palette by track-id hash; the label is
 * `#trk_007 screwdriver`, shifted up to twice to stay inside the canvas.
 */

import { FILL_ALPHA, STROKE_ALPHA, STROKE_WIDTH, trackColour, type OverlayItem } from "./frames";
import { simplifyPolygon, type Point } from "./simplify";

export interface Size {
  width: number;
  height: number;
}

/** 03_UI_Spec §7: polygon tolerance 1.5 px at 720p, scaled with the canvas. */
export const SIMPLIFY_PX_AT_720P = 1.5;
const LABEL_HEIGHT = 18;
const LABEL_PADDING = 4;

export function toPixels(point: [number, number], size: Size): [number, number] {
  return [point[0] * size.width, point[1] * size.height];
}

function boxRing(box: [number, number, number, number]): Point[] {
  const [x0, y0, x1, y1] = box;
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
}

function toleranceFor(size: Size): number {
  return SIMPLIFY_PX_AT_720P * (size.height / 720);
}

function ringOf(item: OverlayItem, size: Size): Point[] {
  const normalised = item.poly && item.poly.length >= 3 ? item.poly : boxRing(item.box);
  return simplifyPolygon(
    normalised.map((point) => toPixels(point, size)),
    toleranceFor(size),
  );
}

function drawLabel(
  ctx: CanvasRenderingContext2D,
  text: string,
  left: number,
  top: number,
  size: Size,
): void {
  const width = ctx.measureText(text).width + LABEL_PADDING * 2;
  const x = Math.min(left, Math.max(0, size.width - width));
  const y = Math.max(0, Math.min(top - LABEL_HEIGHT, size.height - LABEL_HEIGHT));
  ctx.fillStyle = "rgba(11, 15, 20, 0.8)";
  ctx.fillRect(x, y, width, LABEL_HEIGHT);
  ctx.fillStyle = "#E6EDF3";
  ctx.fillText(text, x + LABEL_PADDING, y + LABEL_HEIGHT - 5);
}

/** Paint one frame; returns how many tracks were drawn. */
export function drawOverlay(
  ctx: CanvasRenderingContext2D,
  items: OverlayItem[],
  size: Size,
): number {
  if (items.length === 0) return 0;
  ctx.clearRect(0, 0, size.width, size.height);

  for (const item of items) {
    const ring = ringOf(item, size);
    const colour = trackColour(item.trackId);
    const [x0, y0] = toPixels([item.box[0], item.box[1]], size);
    const [x1, y1] = toPixels([item.box[2], item.box[3]], size);

    ctx.globalAlpha = FILL_ALPHA;
    ctx.fillStyle = colour;
    if (item.poly && item.poly.length >= 3) {
      ctx.beginPath();
      ctx.moveTo(ring[0]?.[0] ?? 0, ring[0]?.[1] ?? 0);
      for (const [x, y] of ring.slice(1)) ctx.lineTo(x, y);
      ctx.closePath();
      ctx.fill();
    } else {
      ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
    }

    ctx.globalAlpha = STROKE_ALPHA;
    ctx.strokeStyle = colour;
    ctx.lineWidth = STROKE_WIDTH;
    if (item.poly && item.poly.length >= 3) {
      ctx.beginPath();
      ctx.moveTo(ring[0]?.[0] ?? 0, ring[0]?.[1] ?? 0);
      for (const [x, y] of ring.slice(1)) ctx.lineTo(x, y);
      ctx.closePath();
      ctx.stroke();
    } else {
      ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
    }

    ctx.globalAlpha = 1;
    ctx.font = "12px ui-monospace, monospace";
    drawLabel(ctx, `#${item.trackId} ${item.concept}`, x0, y0 - 4, size);
  }

  return items.length;
}

function pointInPolygon(x: number, y: number, ring: Array<[number, number]>): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i] as [number, number];
    const [xj, yj] = ring[j] as [number, number];
    const intersects = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

function area(item: OverlayItem): number {
  return Math.abs(item.box[2] - item.box[0]) * Math.abs(item.box[3] - item.box[1]);
}

/** The smallest track under a normalised point (canvas hover / click). */
export function hitTest(
  items: OverlayItem[],
  _size: Size,
  x: number,
  y: number,
): OverlayItem | null {
  let best: OverlayItem | null = null;
  for (const item of items) {
    const inside =
      item.poly && item.poly.length >= 3
        ? pointInPolygon(x, y, item.poly as Array<[number, number]>)
        : x >= item.box[0] && x <= item.box[2] && y >= item.box[1] && y <= item.box[3];
    if (!inside) continue;
    if (best === null || area(item) < area(best)) best = item;
  }
  return best;
}
