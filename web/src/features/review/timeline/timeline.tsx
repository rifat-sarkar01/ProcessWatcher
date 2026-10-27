import { deviationLabel, TYPE_CLASS, type TimelineData } from "./data";
import { timeToPercent } from "./scale";

export type {
  DeviationStatus,
  DeviationType,
  ExpectedStep,
  ObservedInterval,
  TimelineData,
  TimelineDeviation,
} from "./data";


export interface TimelineProps {
  data: TimelineData;
  currentTime: number;
  onSeek: (t: number) => void;
}

/**
 * Dual-lane timeline: the SOP order on top, what was observed below, deviation
 * markers over both, and a playhead. Positions are percentages, so the component
 * needs no measurement and stays testable.
 */
export function Timeline({ data, currentTime, onSeek }: TimelineProps) {
  const { duration_s: duration, expected, observed, deviations } = data;
  const slot = expected.length > 0 ? 100 / expected.length : 0;

  return (
    <div className="relative space-y-2 pt-6" data-testid="timeline">
      <div
        className="relative h-12 rounded-control border border-border bg-surface"
        role="group"
        aria-label="Expected steps"
      >
        {expected.map((step, index) => (
          <div
            key={step.step_id}
            className="absolute top-0 flex h-full items-center justify-center border-r border-border text-small text-muted last:border-r-0"
            style={{ left: `${index * slot}%`, width: `${slot}%` }}
            title={`Expected step ${step.idx}: ${step.step_id}`}
          >
            {step.step_id}
          </div>
        ))}
      </div>

      <div
        className="relative h-12 overflow-hidden rounded-control border border-border bg-surface-2"
        role="group"
        aria-label="Observed segments"
      >
        {observed.map((interval) => {
          const left = timeToPercent(interval.t_start, duration);
          const width = timeToPercent(interval.t_end, duration) - left;
          return (
            <div
              key={interval.interval_id}
              data-testid="observed-block"
              className={
                interval.step_id
                  ? "absolute top-0 flex h-full items-center justify-center border-r border-border bg-accent/20 text-small text-fg"
                  : "absolute top-0 flex h-full items-center justify-center border border-dashed border-border text-small text-muted"
              }
              style={{ left: `${left}%`, width: `${Math.max(width, 0)}%` }}
              title={interval.step_id ?? "idle"}
            >
              {interval.step_id ?? "idle"}
            </div>
          );
        })}
      </div>

      <div
        data-testid="playhead"
        className="pointer-events-none absolute top-0 bottom-0 w-0.5 bg-accent"
        style={{ left: `${timeToPercent(currentTime, duration)}%` }}
      />

      <div className="relative h-8" role="group" aria-label="Deviations">
        {deviations.map((deviation) => (
          <button
            key={deviation.id}
            type="button"
            data-testid="deviation-marker"
            data-status={deviation.status}
            aria-label={deviationLabel(deviation)}
            onClick={() => onSeek(deviation.t_start)}
            style={{ left: `${timeToPercent(deviation.t_start, duration)}%` }}
            className={`absolute top-0 h-8 w-4 -translate-x-1/2 border-2 bg-surface ${
              TYPE_CLASS[deviation.type]
            } ${
              deviation.status === "needs_review"
                ? "border-dashed border-needs-review"
                : "border-solid"
            }`}
          />
        ))}
      </div>
    </div>
  );
}
