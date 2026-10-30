import { useState } from "react";

import type { EvidenceItem } from "../../../types/generated/report";
import { formatTimecode } from "../timeline/format";

const NAV_BUTTON =
  "rounded-control border border-border-strong px-3 py-1 text-small text-fg disabled:opacity-50";

export interface EvidenceCarouselProps {
  items: readonly EvidenceItem[];
  stepId: string;
  artifactUrl?: (path: string) => string;
}

function resolve(artifactUrl: ((path: string) => string) | undefined, path: string): string {
  return artifactUrl ? artifactUrl(path) : path;
}

/**
 * Real frames only (03_UI_Spec §6): the carousel never holds an illustration, and
 * every frame carries a provenance tag and a meaningful alt text.
 */
export function EvidenceCarousel({ items, stepId, artifactUrl }: EvidenceCarouselProps) {
  const [requested, setRequested] = useState(0);
  if (items.length === 0) return null;

  const index = Math.min(requested, items.length - 1);
  const item = items[index]!;

  return (
    <div role="group" aria-label="Evidence carousel" className="space-y-2">
      <div className="relative">
        <img
          src={resolve(artifactUrl, item.output_path)}
          alt={`Evidence frame at ${formatTimecode(item.t)}, step ${stepId}`}
          className="w-full rounded-control border-2 border-fg"
        />
        <span className="absolute left-2 top-2 rounded-chip bg-bg/80 px-2 py-1 font-mono text-small">
          {`EVIDENCE · real frame · ${formatTimecode(item.t)}`}
        </span>
      </div>

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label="Previous evidence frame"
          className={NAV_BUTTON}
          disabled={index === 0}
          onClick={() => setRequested(index - 1)}
        >
          Previous
        </button>
        <p aria-live="polite" className="m-0 text-small text-muted">
          {`Evidence ${index + 1} of ${items.length}`}
        </p>
        <button
          type="button"
          aria-label="Next evidence frame"
          className={NAV_BUTTON}
          disabled={index === items.length - 1}
          onClick={() => setRequested(index + 1)}
        >
          Next
        </button>
      </div>

      <p className="m-0 font-mono text-small text-muted">{`step ${stepId}`}</p>

      {item.clip ? (
        <video
          controls
          src={resolve(artifactUrl, item.clip.path)}
          aria-label={`Evidence clip from ${formatTimecode(item.clip.t_start)} to ${formatTimecode(item.clip.t_end)}`}
          className="w-full rounded-control"
        />
      ) : null}
    </div>
  );
}
