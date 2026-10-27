/**
 * Keyboard transport for the review player (03_UI_Spec.md §6, 02_AppFlow §2.4).
 *
 * Pure mapping so shortcuts are unit-tested without a DOM:
 * J/L scrub ±1 s, K toggles playback, ←/→ step one frame (shift: one second),
 * N/P jump to the next/previous deviation.
 */

export interface KeyboardDeviation {
  id: string;
  t_start: number;
}

export type PlayerAction =
  | { type: "seek-by"; delta: number }
  | { type: "toggle-play" }
  | { type: "next-deviation" }
  | { type: "previous-deviation" };

export interface KeyboardOptions {
  shiftKey?: boolean;
}

export function resolveKeyboardAction(
  key: string,
  fps: number,
  options: KeyboardOptions = {},
): PlayerAction | null {
  if (!(fps > 0)) throw new RangeError("fps must be positive");

  const shift = options.shiftKey ?? false;
  const normalised = key.length === 1 ? key.toLowerCase() : key;

  switch (normalised) {
    case "j":
      return { type: "seek-by", delta: -1 };
    case "l":
      return { type: "seek-by", delta: 1 };
    case "k":
      return { type: "toggle-play" };
    case "n":
      return { type: "next-deviation" };
    case "p":
      return { type: "previous-deviation" };
    case "ArrowLeft":
      return { type: "seek-by", delta: shift ? -1 : -1 / fps };
    case "ArrowRight":
      return { type: "seek-by", delta: shift ? 1 : 1 / fps };
    default:
      return null;
  }
}

const EPSILON_S = 1e-6;

/** The first deviation that starts after `currentTime`, or null at the end. */
export function nextDeviation<T extends KeyboardDeviation>(
  deviations: readonly T[],
  currentTime: number,
): T | null {
  let best: T | null = null;
  for (const deviation of deviations) {
    if (deviation.t_start > currentTime + EPSILON_S) {
      if (best === null || deviation.t_start < best.t_start) best = deviation;
    }
  }
  return best;
}

/** The last deviation that starts before `currentTime`, or null before the first. */
export function previousDeviation<T extends KeyboardDeviation>(
  deviations: readonly T[],
  currentTime: number,
): T | null {
  let best: T | null = null;
  for (const deviation of deviations) {
    if (deviation.t_start < currentTime - EPSILON_S) {
      if (best === null || deviation.t_start > best.t_start) best = deviation;
    }
  }
  return best;
}
