/**
 * Time ↔ pixel mapping for the review timeline.
 *
 * One scale object owns the conversion so the ruler, lanes, markers and playhead all
 * agree, and so the mapping can be unit-tested without a browser layout.
 */

export interface TimeScaleOptions {
  padding?: number;
}

export interface TimeScale {
  duration: number;
  width: number;
  padding: number;
  /** Seconds → pixels, clamped to the clip. */
  timeToX(t: number): number;
  /** Pixels → seconds, clamped to the clip. */
  xToTime(x: number): number;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

export function createTimeScale(
  duration: number,
  width: number,
  options: TimeScaleOptions = {},
): TimeScale {
  const padding = options.padding ?? 0;
  if (!(duration > 0)) throw new RangeError("duration must be positive");
  if (!(width > 0)) throw new RangeError("width must be positive");

  const usable = width - 2 * padding;
  if (!(usable > 0)) throw new RangeError("width must be larger than twice the padding");

  return {
    duration,
    width,
    padding,
    timeToX(t: number): number {
      return padding + (clamp(t, 0, duration) / duration) * usable;
    },
    xToTime(x: number): number {
      return ((clamp(x, padding, padding + usable) - padding) / usable) * duration;
    },
  };
}

/** Seconds → percentage of the clip (0–100), for CSS-positioned lanes and markers. */
export function timeToPercent(t: number, duration: number): number {
  if (!(duration > 0)) return 0;
  return clamp(t / duration, 0, 1) * 100;
}
