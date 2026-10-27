import { useCallback, useEffect, useState } from "react";

import { Timeline, type TimelineData } from "../timeline/timeline";
import { nextDeviation, previousDeviation, resolveKeyboardAction } from "./keyboard";
import { ReviewPlayer } from "./player";

export interface ReviewSurfaceProps {
  src: string;
  data: TimelineData;
  fps?: number;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

/**
 * The review core: player + dual-lane timeline kept in sync, with the keyboard
 * transport from 03_UI_Spec §6. State lives here so scrubbing, marker clicks and
 * shortcuts all move the same clock.
 */
export function ReviewSurface({ src, data, fps = 15 }: ReviewSurfaceProps) {
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);

  const duration = data.duration_s;
  const seek = useCallback(
    (value: number) => setCurrentTime(clamp(value, 0, duration)),
    [duration],
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isEditableTarget(event.target)) return;

      const action = resolveKeyboardAction(event.key, fps, { shiftKey: event.shiftKey });
      if (action === null) return;
      event.preventDefault();

      switch (action.type) {
        case "seek-by":
          seek(currentTime + action.delta);
          break;
        case "toggle-play":
          setPlaying((value) => !value);
          break;
        case "next-deviation": {
          const match = nextDeviation(data.deviations, currentTime);
          if (match) seek(match.t_start);
          break;
        }
        case "previous-deviation": {
          const match = previousDeviation(data.deviations, currentTime);
          if (match) seek(match.t_start);
          break;
        }
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [currentTime, data.deviations, fps, seek]);

  return (
    <div className="space-y-4">
      <ReviewPlayer
        src={src}
        currentTime={currentTime}
        fps={fps}
        playing={playing}
        playbackRate={playbackRate}
        onSeek={seek}
        onTogglePlay={() => setPlaying((value) => !value)}
        onPlaybackRateChange={setPlaybackRate}
      />
      <Timeline data={data} currentTime={currentTime} onSeek={seek} />
    </div>
  );
}
