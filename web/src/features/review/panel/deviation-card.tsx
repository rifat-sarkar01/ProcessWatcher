import { useState } from "react";

import type { Deviation } from "../../../types/generated/report";
import { TYPE_LABEL, type DeviationType } from "../timeline/data";
import { formatTimecode } from "../timeline/format";

import { EvidenceCarousel } from "./evidence-carousel";
import {
  confidencePercent,
  DECISION_LABEL,
  SEVERITY_LABEL,
  TYPE_CHIP_CLASS,
  type ReviewDecision,
} from "./panel-data";

const ACTION_BUTTON =
  "rounded-control border border-border-strong px-3 py-1 text-small text-fg aria-pressed:border-accent aria-pressed:text-accent";

function TypeIcon({ type }: { type: DeviationType }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: "0 0 20 20",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
  };
  if (type === "missed") {
    return (
      <svg {...common}>
        <path d="M5 4l6 6-6 6z" />
        <path d="M14 4v12" />
      </svg>
    );
  }
  if (type === "out_of_order") {
    return (
      <svg {...common}>
        <path d="M3 7h11l-3-3" />
        <path d="M17 13H6l3 3" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M12.5 3.5l4 4-6.5 6.5-3 1 1-3z" />
      <path d="M3 17l3.5-3.5" />
      <path d="M3 3l3 3M6 3l-3 3" />
    </svg>
  );
}

export interface DeviationCardProps {
  deviation: Deviation;
  title: string;
  decision?: ReviewDecision;
  note?: string;
  artifactUrl?: (path: string) => string;
  onSeek?: (t: number) => void;
  onDecide?: (id: string, decision: ReviewDecision) => void;
  onNote?: (id: string, note: string) => void;
}

/** One deviation: what happened, the real-frame evidence and the reviewer's call. */
export function DeviationCard({
  deviation,
  title,
  decision,
  note,
  artifactUrl,
  onSeek,
  onDecide,
  onNote,
}: DeviationCardProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(note ?? "");
  const pct = confidencePercent(deviation.confidence);
  const review = deviation.status === "needs_review";

  return (
    <li
      data-testid={`deviation-${deviation.id}`}
      className={`space-y-3 rounded-card border bg-surface p-4 ${
        review ? "border-2 border-dashed border-needs-review" : "border-border"
      }`}
    >
      <h3 className="m-0 text-base font-semibold">{title}</h3>

      <div className="flex flex-wrap items-center gap-3 text-small">
        <span
          className={`inline-flex items-center gap-1 rounded-chip border px-[10px] py-0.5 ${TYPE_CHIP_CLASS[deviation.type]}`}
        >
          <TypeIcon type={deviation.type} />
          {TYPE_LABEL[deviation.type]}
        </span>
        <span className={`inline-flex items-center gap-1 ${deviation.severity === "high" ? "text-fg" : "text-muted"}`}>
          {deviation.severity === "high" ? (
            <span aria-hidden="true" className="inline-block h-2 w-2 rounded-full bg-current" />
          ) : null}
          {SEVERITY_LABEL[deviation.severity]}
        </span>
        <button
          type="button"
          aria-label={`Seek to ${formatTimecode(deviation.t_start)}`}
          className="rounded-control font-mono text-small text-accent underline-offset-4 hover:underline"
          onClick={() => onSeek?.(deviation.t_start)}
        >
          {formatTimecode(deviation.t_start)}
        </button>
        <span className="inline-flex items-center gap-2">
          <span
            role="meter"
            aria-label="Confidence"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            aria-valuetext={`${pct}%`}
            className="inline-block h-1.5 w-16 overflow-hidden rounded-chip bg-surface-2"
          >
            <span className="block h-full rounded-chip bg-accent" style={{ width: `${pct}%` }} />
          </span>
          <span className="font-mono text-muted">{`${pct}%`}</span>
        </span>
      </div>

      {review ? (
        <p className="m-0 text-small text-needs-review">
          Needs review: the evidence is not conclusive.
        </p>
      ) : null}

      <p className="m-0">{deviation.explanation}</p>

      {deviation.evidence_unavailable ? (
        <div role="alert" className="rounded-control border border-dev-missed/60 bg-dev-missed/10 px-3 py-2 text-small">
          Evidence could not be extracted for this deviation.
        </div>
      ) : (
        <EvidenceCarousel
          items={deviation.evidence}
          stepId={deviation.step_id}
          artifactUrl={artifactUrl}
        />
      )}

      {deviation.illustration ? (
        <figure className="m-0 rounded-card border-2 border-dashed border-illustration p-2">
          <span className="inline-block rounded-chip border border-illustration bg-illustration/[0.16] px-2 py-0.5 font-mono text-small text-illustration">
            AI ILLUSTRATION · NOT EVIDENCE
          </span>
          {deviation.illustration.path ? (
            <img
              src={artifactUrl ? artifactUrl(deviation.illustration.path) : deviation.illustration.path}
              alt={`AI illustration, not evidence: ${title}`}
              className="mt-2 w-full rounded-control"
            />
          ) : null}
          <figcaption className="mt-2 text-small text-muted">
            What correct looks like (AI illustration, not evidence)
          </figcaption>
        </figure>
      ) : deviation.illustration_unavailable_reason ? (
        <p className="m-0 text-small text-muted">{deviation.illustration_unavailable_reason}</p>
      ) : null}

      <footer className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <button
          type="button"
          aria-label={`Accept ${deviation.id}`}
          aria-pressed={decision === "accepted"}
          className={ACTION_BUTTON}
          onClick={() => onDecide?.(deviation.id, "accepted")}
        >
          Accept
        </button>
        <button
          type="button"
          aria-label={`Dismiss ${deviation.id}`}
          aria-pressed={decision === "dismissed"}
          className={ACTION_BUTTON}
          onClick={() => onDecide?.(deviation.id, "dismissed")}
        >
          Dismiss
        </button>
        <button
          type="button"
          aria-label={`Add note ${deviation.id}`}
          aria-expanded={editing}
          className={ACTION_BUTTON}
          onClick={() => setEditing((value) => !value)}
        >
          Add note
        </button>
        {decision ? (
          <span data-testid={`decision-${deviation.id}`} className="text-small text-muted">
            {DECISION_LABEL[decision]}
          </span>
        ) : null}
      </footer>

      {editing ? (
        <div className="space-y-2">
          <label htmlFor={`note-${deviation.id}`} className="text-small text-muted">
            Note
          </label>
          <textarea
            id={`note-${deviation.id}`}
            aria-label={`Note for ${deviation.id}`}
            value={draft}
            rows={2}
            className="w-full rounded-control border border-border-strong bg-bg px-3 py-2 text-control text-fg"
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className="flex gap-2">
            <button
              type="button"
              aria-label={`Save note ${deviation.id}`}
              className={ACTION_BUTTON}
              onClick={() => {
                onNote?.(deviation.id, draft.trim());
                setEditing(false);
              }}
            >
              Save note
            </button>
            <button
              type="button"
              aria-label={`Cancel note ${deviation.id}`}
              className={ACTION_BUTTON}
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {note ? (
        <p data-testid={`deviation-note-${deviation.id}`} className="m-0 text-small text-muted">
          {`Note: ${note}`}
        </p>
      ) : null}
    </li>
  );
}
