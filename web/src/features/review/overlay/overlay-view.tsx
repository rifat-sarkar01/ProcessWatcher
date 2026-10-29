/**
 * SAM overlay + track inspector (`02_AppFlow.md` §2.4, `03_UI_Spec.md` §6–§7).
 *
 * The canvas sits on top of the video and is repainted from `tracks.json` at the
 * playhead (or on `requestVideoFrameCallback` when the caller supplies the element).
 * Toggles hide a whole concept or a single track; hovering names the track under the
 * cursor; the inspector lists each track's holds with its mean confidence.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Track } from "../../../types/generated/tracks";

import { drawOverlay, hitTest, type Size } from "./draw";
import { conceptsOf, frameAt, holdsOf } from "./frames";
import { formatTimecode } from "../timeline/format";

export interface OverlayViewProps {
  tracks: Track[];
  currentTime: number;
  fps: number;
  width?: number;
  height?: number;
  /** The player's video element, used for frame-accurate repaint when available. */
  video?: HTMLVideoElement | null;
  onSelectTrack?: (trackId: string) => void;
  /** Test seam: swap the painter for a spy. */
  draw?: typeof drawOverlay;
  /** Test seam: jsdom has no canvas, so tests inject a stub 2D context. */
  contextFor?: (canvas: HTMLCanvasElement) => CanvasRenderingContext2D | null;
}

const TOGGLE_CLASS =
  "min-h-11 rounded-control border px-3 text-small transition-colors duration-fast hover:bg-surface-2";
const TOGGLE_ON = "border-accent text-fg";
const TOGGLE_OFF = "border-border text-muted";

export function OverlayView({
  tracks,
  currentTime,
  fps,
  width = 1280,
  height = 720,
  video = null,
  onSelectTrack,
  draw = drawOverlay,
  contextFor = (canvas) => canvas.getContext("2d"),
}: OverlayViewProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const [hiddenConcepts, setHiddenConcepts] = useState<string[]>([]);
  const [hiddenTracks, setHiddenTracks] = useState<string[]>([]);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  // Frame-callback time wins while a video is attached; the prop is the fallback.
  const [videoTime, setVideoTime] = useState<number | null>(null);

  useEffect(() => {
    const target = video as (HTMLVideoElement & {
      requestVideoFrameCallback?: (callback: () => void) => number;
      cancelVideoFrameCallback?: (handle: number) => void;
    }) | null;
    if (!target?.requestVideoFrameCallback) return;

    let handle = 0;
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      setVideoTime(target.currentTime);
      handle = target.requestVideoFrameCallback?.(tick) ?? 0;
    };
    handle = target.requestVideoFrameCallback(tick);
    return () => {
      cancelled = true;
      target.cancelVideoFrameCallback?.(handle);
    };
  }, [video]);

  const size: Size = useMemo(() => ({ width, height }), [width, height]);
  const liveTime = videoTime ?? currentTime;

  const items = useMemo(() => {
    const visible = tracks.filter(
      (track) => !hiddenTracks.includes(track.id) && !hiddenConcepts.includes(track.concept),
    );
    return frameAt(visible, liveTime, fps);
  }, [tracks, hiddenTracks, hiddenConcepts, liveTime, fps]);

  const hovered = useMemo(
    () => items.find((item) => item.trackId === hoveredId) ?? null,
    [items, hoveredId],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas ? contextFor(canvas) : null;
    if (!ctx) return;
    draw(ctx, items, size);
  }, [items, size, draw, contextFor]);

  const pointerAt = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>): { x: number; y: number } => {
      const canvas = event.currentTarget;
      const rect = canvas.getBoundingClientRect();
      const boxWidth = rect.width || canvas.width || width;
      const boxHeight = rect.height || canvas.height || height;
      return {
        x: (event.clientX - rect.left) / boxWidth,
        y: (event.clientY - rect.top) / boxHeight,
      };
    },
    [width, height],
  );

  const toggleConcept = (concept: string) => {
    setHiddenConcepts((current) =>
      current.includes(concept)
        ? current.filter((value) => value !== concept)
        : [...current, concept],
    );
  };

  const toggleTrack = (trackId: string) => {
    setHiddenTracks((current) =>
      current.includes(trackId)
        ? current.filter((value) => value !== trackId)
        : [...current, trackId],
    );
  };

  const concepts = conceptsOf(tracks);

  return (
    <section className="space-y-3" aria-label="Track overlay">
      <div className="relative">
        <canvas
          ref={canvasRef}
          data-testid="overlay-canvas"
          role="img"
          aria-label={`Track overlay with ${items.length} visible track${items.length === 1 ? "" : "s"}`}
          width={width}
          height={height}
          className="absolute inset-0 h-full w-full"
          onMouseMove={(event) => {
            const { x, y } = pointerAt(event);
            setHoveredId(hitTest(items, size, x, y)?.trackId ?? null);
          }}
          onMouseLeave={() => setHoveredId(null)}
          onClick={(event) => {
            const { x, y } = pointerAt(event);
            const target = hitTest(items, size, x, y);
            if (target) onSelectTrack?.(target.trackId);
          }}
        />
        {hovered ? (
          <span
            data-testid="overlay-hover-label"
            className="pointer-events-none absolute left-2 top-2 rounded-control bg-bg/80 px-2 py-1 font-mono text-small text-fg"
          >
            #{hovered.trackId} {hovered.concept}
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-small text-muted">Concepts</span>
        {concepts.map(({ concept }) => {
          const on = !hiddenConcepts.includes(concept);
          return (
            <button
              key={concept}
              type="button"
              aria-pressed={on}
              className={`${TOGGLE_CLASS} ${on ? TOGGLE_ON : TOGGLE_OFF}`}
              onClick={() => toggleConcept(concept)}
            >
              {concept}
            </button>
          );
        })}
      </div>

      {tracks.length === 0 ? (
        <p className="m-0 text-small text-muted">No tracks were found in this run.</p>
      ) : (
        <ul aria-label="Track inspector" className="m-0 list-none space-y-2 p-0">
          {tracks.map((track) => {
            const holds = holdsOf(track);
            const meanScore =
              holds.reduce((total, hold) => total + hold.meanScore * hold.samples, 0) /
              Math.max(
                1,
                holds.reduce((total, hold) => total + hold.samples, 0),
              );
            const hidden = hiddenTracks.includes(track.id);
            return (
              <li
                key={track.id}
                aria-label={`${track.id} ${track.concept}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-control border border-border bg-surface px-3 py-2 text-small"
              >
                <span className="font-mono text-fg">#{track.id}</span>
                <span className="text-muted">{track.concept}</span>
                <span className="text-muted">
                  {holds.length} hold{holds.length === 1 ? "" : "s"}
                </span>
                <span className="font-mono text-muted">
                  {holds.length > 0
                    ? `${formatTimecode(holds[0]!.tStart)} – ${formatTimecode(holds[0]!.tEnd)}`
                    : "–"}
                </span>
                <span className="font-mono text-fg">{Math.round(meanScore * 100)}%</span>
                <button
                  type="button"
                  className={`${TOGGLE_CLASS} ${hidden ? TOGGLE_OFF : TOGGLE_ON}`}
                  aria-pressed={!hidden}
                  aria-label={`${hidden ? "Show" : "Hide"} ${track.id}`}
                  onClick={() => toggleTrack(track.id)}
                >
                  {hidden ? "Show" : "Hide"}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
