import { useState } from "react";

import type { Report } from "../../../types/generated/report";
import { Banner, EmptyState } from "../../../ui/states";

import { DeviationCard } from "./deviation-card";
import {
  FILTERS,
  deviationTitle,
  filterDeviations,
  partialNotice,
  sortDeviations,
  type DecisionMap,
  type DeviationFilter,
  type NoteMap,
  type ReviewDecision,
  type SortMode,
} from "./panel-data";

const FILTER_BUTTON =
  "rounded-chip border border-border-strong px-3 py-1 text-small text-fg aria-pressed:border-accent aria-pressed:bg-accent/10 aria-pressed:text-accent";

export interface DeviationPanelProps {
  report: Report;
  artifactUrl?: (path: string) => string;
  initialDecisions?: DecisionMap;
  initialNotes?: NoteMap;
  onSeek?: (t: number) => void;
  onDecide?: (id: string, decision: ReviewDecision) => void;
  onNote?: (id: string, note: string) => void;
  onExport?: () => void;
}

/**
 * The review panel from 03_UI_Spec §5–§6: deviation cards, filters and the reviewer's
 * accept/dismiss/note decisions. Review state is local until T-5.3's PATCH endpoint
 * lands; the callbacks are the seam for that endpoint.
 */
export function DeviationPanel({
  report,
  artifactUrl,
  initialDecisions,
  initialNotes,
  onSeek,
  onDecide,
  onNote,
  onExport,
}: DeviationPanelProps) {
  const [decisions, setDecisions] = useState<DecisionMap>(initialDecisions ?? {});
  const [notes, setNotes] = useState<NoteMap>(initialNotes ?? {});
  const [filter, setFilter] = useState<DeviationFilter>("all");
  const [sort, setSort] = useState<SortMode>("time");

  const stepIdx = new Map(report.sop.steps.map((step) => [step.id, step.idx]));
  const visible = filterDeviations(sortDeviations(report.deviations, sort), filter);
  const partial = partialNotice(report.degraded_stages);
  const summary = `${report.summary.flagged} flagged · ${report.summary.needs_review} needs review`;

  function decide(id: string, decision: ReviewDecision): void {
    setDecisions((previous) => ({ ...previous, [id]: decision }));
    onDecide?.(id, decision);
  }

  function saveNote(id: string, note: string): void {
    setNotes((previous) => ({ ...previous, [id]: note }));
    onNote?.(id, note);
  }

  return (
    <section
      aria-labelledby="deviation-panel-title"
      className="space-y-4 rounded-card border border-border bg-surface p-4"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="deviation-panel-title" className="m-0 text-h2 font-semibold">
            Deviations
          </h2>
          <p className="m-0 text-small text-muted">{summary}</p>
        </div>
        {onExport ? (
          <button
            type="button"
            className="min-h-[44px] rounded-control bg-accent px-4 text-control font-semibold text-accent-ink"
            onClick={onExport}
          >
            Export report
          </button>
        ) : null}
      </header>

      {partial ? <Banner tone="warning">{partial}</Banner> : null}

      {report.status === "not_recognized" ? (
        <Banner tone="error">This video does not match the SOP closely enough to check it.</Banner>
      ) : report.deviations.length === 0 ? (
        report.status === "done" ? (
          <EmptyState title="No deviations found." help="Every step was observed in order." />
        ) : null
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div role="group" aria-label="Filter deviations" className="flex flex-wrap gap-2">
              {FILTERS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={filter === option.value}
                  className={FILTER_BUTTON}
                  onClick={() => setFilter(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div role="group" aria-label="Sort deviations" className="flex gap-2">
              <button
                type="button"
                aria-pressed={sort === "time"}
                className={FILTER_BUTTON}
                onClick={() => setSort("time")}
              >
                By time
              </button>
              <button
                type="button"
                aria-pressed={sort === "severity"}
                className={FILTER_BUTTON}
                onClick={() => setSort("severity")}
              >
                By severity
              </button>
            </div>
          </div>

          {visible.length === 0 ? (
            <p className="m-0 text-muted">No deviations match this filter.</p>
          ) : (
            <ol aria-label="Deviations" className="m-0 list-none space-y-3 p-0">
              {visible.map((deviation) => (
                <DeviationCard
                  key={deviation.id}
                  deviation={deviation}
                  title={deviationTitle(
                    deviation,
                    stepIdx.get(deviation.step_id) ?? null,
                    deviation.relates_to_step_id
                      ? (stepIdx.get(deviation.relates_to_step_id) ?? null)
                      : null,
                  )}
                  decision={decisions[deviation.id]}
                  note={notes[deviation.id]}
                  artifactUrl={artifactUrl}
                  onSeek={onSeek}
                  onDecide={decide}
                  onNote={saveNote}
                />
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  );
}
