/**
 * Overlay geometry: which SAM track samples are visible at time `t`, the overlay colour
 * per track (03_UI_Spec §2 palette, chosen by track-id hash) and the holds the track
 * inspector lists.
 *
 * Frame indices live in `tracks.json`; the UI works in seconds only.
 */

import type { Track } from "../../../types/generated/tracks";

/** 03_UI_Spec §2 "Overlay palette"; canvas needs literal colours, components use tokens. */
export const OVERLAY_PALETTE = [
  "#22D3EE",
  "#F472B6",
  "#FACC15",
  "#34D399",
  "#FB923C",
  "#60A5FA",
  "#C084FC",
  "#F87171",
  "#2DD4BF",
  "#A3E635",
] as const;

export const FILL_ALPHA = 0.35;
export const STROKE_ALPHA = 0.95;
export const STROKE_WIDTH = 2;

export interface OverlayItem {
  trackId: string;
  concept: string;
  box: [number, number, number, number];
  poly?: Array<[number, number]>;
  score: number;
}

export interface Hold {
  tStart: number;
  tEnd: number;
  samples: number;
  meanScore: number;
}

/** A hold is continuous while consecutive samples stay within this gap. */
export const HOLD_GAP_S = 0.5;

export function trackColour(trackId: string): string {
  let hash = 0;
  for (let index = 0; index < trackId.length; index += 1) {
    hash = (hash * 31 + trackId.charCodeAt(index)) >>> 0;
  }
  return OVERLAY_PALETTE[hash % OVERLAY_PALETTE.length] as string;
}

function toItem(track: Track, sample: Track["frames"][number]): OverlayItem {
  return {
    trackId: track.id,
    concept: track.concept,
    box: sample.box as [number, number, number, number],
    poly: sample.poly as Array<[number, number]> | undefined,
    score: sample.score,
  };
}

/** The sample closest to `t`, or nothing when the track has no sample within a frame. */
function sampleAt(track: Track, t: number, tolerance: number): Track["frames"][number] | null {
  const frames = track.frames;
  if (frames.length === 0) return null;

  let low = 0;
  let high = frames.length - 1;
  while (low < high) {
    const middle = (low + high) >> 1;
    if ((frames[middle] as Track["frames"][number]).t < t) low = middle + 1;
    else high = middle;
  }

  const candidates = [frames[low], frames[Math.max(0, low - 1)]].filter(
    (candidate): candidate is Track["frames"][number] => candidate !== undefined,
  );
  let best: Track["frames"][number] | null = null;
  for (const candidate of candidates) {
    if (Math.abs(candidate.t - t) > tolerance) continue;
    if (best === null || Math.abs(candidate.t - t) < Math.abs(best.t - t)) best = candidate;
  }
  return best;
}

/**
 * Visible overlay items at `t`, sorted by track id for a stable draw order.
 *
 * Tolerance is one source frame (2 / fps) so a 15 fps analysis track keeps a label on
 * screen between samples without smearing it onto the next hold.
 */
export function frameAt(tracks: Track[], t: number, fps: number): OverlayItem[] {
  const tolerance = fps > 0 ? 1 / fps : 0.1;
  const items: OverlayItem[] = [];

  for (const track of [...tracks].sort((a, b) => a.id.localeCompare(b.id))) {
    const sample = sampleAt(track, t, tolerance);
    if (sample) items.push(toItem(track, sample));
  }
  return items;
}

/** Group a track's samples into holds, plus their mean confidence. */
export function holdsOf(track: Track): Hold[] {
  const holds: Hold[] = [];
  let current: { tStart: number; tEnd: number; count: number; score: number } | null = null;

  for (const sample of track.frames) {
    if (current !== null && sample.t - current.tEnd <= HOLD_GAP_S) {
      current.tEnd = sample.t;
      current.count += 1;
      current.score += sample.score;
      continue;
    }
    if (current !== null) {
      holds.push({
        tStart: current.tStart,
        tEnd: current.tEnd,
        samples: current.count,
        meanScore: current.score / current.count,
      });
    }
    current = { tStart: sample.t, tEnd: sample.t, count: 1, score: sample.score };
  }

  if (current !== null) {
    holds.push({
      tStart: current.tStart,
      tEnd: current.tEnd,
      samples: current.count,
      meanScore: current.score / current.count,
    });
  }
  return holds;
}

export interface ConceptSummary {
  concept: string;
  trackIds: string[];
}

export function conceptsOf(tracks: Track[]): ConceptSummary[] {
  const byConcept = new Map<string, string[]>();
  for (const track of tracks) {
    const ids = byConcept.get(track.concept) ?? [];
    ids.push(track.id);
    byConcept.set(track.concept, ids);
  }
  return [...byConcept.entries()]
    .map(([concept, trackIds]) => ({ concept, trackIds: [...trackIds].sort() }))
    .sort((a, b) => a.concept.localeCompare(b.concept));
}
