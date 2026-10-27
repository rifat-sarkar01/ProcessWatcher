import { useEffect, useRef } from "react";

import { formatTimecode } from "../timeline/format";

const PLAYBACK_RATES = [0.25, 0.5, 1, 2] as const;

export interface ReviewPlayerProps {
  src: string;
  currentTime: number;
  fps: number;
  playing: boolean;
  playbackRate: number;
  onSeek: (t: number) => void;
  onTogglePlay: () => void;
  onPlaybackRateChange: (rate: number) => void;
}

const CONTROL_CLASS =
  "min-h-11 rounded-control border border-border-strong px-3 text-control text-fg hover:bg-surface-2";

/**
 * Custom transport around a plain `<video>`: frame step, ±1 s, play/pause and speed.
 * The element stays unmuted-agnostic; overlays are drawn by T-5.10 on top of it.
 */
export function ReviewPlayer({
  src,
  currentTime,
  fps,
  playing,
  playbackRate,
  onSeek,
  onTogglePlay,
  onPlaybackRateChange,
}: ReviewPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (video && Math.abs(video.currentTime - currentTime) > 1e-3) {
      video.currentTime = currentTime;
    }
  }, [currentTime]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (playing) {
      const promise = video.play();
      if (promise && typeof promise.catch === "function") void promise.catch(() => {});
    } else {
      video.pause();
    }
  }, [playing]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = playbackRate;
  }, [playbackRate]);

  const frame = 1 / fps;

  return (
    <div className="space-y-2">
      <video
        ref={videoRef}
        data-testid="review-video"
        src={src}
        className="w-full rounded-control border border-border bg-black"
        preload="metadata"
      />
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={CONTROL_CLASS} aria-label="Back one second" onClick={() => onSeek(currentTime - 1)}>
          −1 s
        </button>
        <button type="button" className={CONTROL_CLASS} aria-label="Back one frame" onClick={() => onSeek(currentTime - frame)}>
          −1 f
        </button>
        <button type="button" className={CONTROL_CLASS} aria-label={playing ? "Pause" : "Play"} onClick={onTogglePlay}>
          {playing ? "Pause" : "Play"}
        </button>
        <button type="button" className={CONTROL_CLASS} aria-label="Forward one frame" onClick={() => onSeek(currentTime + frame)}>
          +1 f
        </button>
        <button type="button" className={CONTROL_CLASS} aria-label="Forward one second" onClick={() => onSeek(currentTime + 1)}>
          +1 s
        </button>

        <label className="ml-2 text-small text-muted">
          Speed
          <select
            aria-label="Playback speed"
            className="ml-2 rounded-control border border-border-strong bg-bg px-2 py-1 text-control text-fg"
            value={playbackRate}
            onChange={(event) => onPlaybackRateChange(Number(event.target.value))}
          >
            {PLAYBACK_RATES.map((rate) => (
              <option key={rate} value={rate}>
                {rate}×
              </option>
            ))}
          </select>
        </label>

        <output data-testid="current-time" className="ml-auto font-mono text-small tabular-nums">
          {formatTimecode(currentTime)}
        </output>
      </div>
    </div>
  );
}
