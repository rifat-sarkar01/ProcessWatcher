import { EmptyState } from "../../ui/states";
import { DEMO_CASES, type DemoCase } from "./cases";

export interface DemoGalleryProps {
  cases?: readonly DemoCase[];
  onOpen: (caseId: string) => void;
}

function findingCount(count: number): string {
  return `${count} finding${count === 1 ? "" : "s"}`;
}

function durationLabel(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

/**
 * `/demo`: the three frozen cases with an offline badge (FR-14).
 *
 * "Offline" is a promise, not decoration: every case renders from committed data, so
 * the demo keeps working with no network and no model spend.
 */
export function DemoGallery({ cases = DEMO_CASES, onOpen }: DemoGalleryProps) {
  if (cases.length === 0) {
    return (
      <EmptyState
        title="No demo cases"
        help="Frozen demo cases are produced by pw demo-build (T-7.1)."
      />
    );
  }

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="m-0 text-h2 font-semibold">Demo cases</h2>
        <span className="rounded-chip border border-illustration px-2 py-0.5 text-small text-illustration">
          Offline
        </span>
      </header>

      <p className="m-0 max-w-3xl text-muted">
        Three frozen cases checked into the repo, with <strong>no network or model calls</strong>, so
        the demo cannot fail on stage.
      </p>

      <ul className="m-0 grid list-none gap-3 p-0 md:grid-cols-2 xl:grid-cols-3">
        {cases.map((demoCase) => (
          <li key={demoCase.id}>
            <button
              type="button"
              onClick={() => onOpen(demoCase.id)}
              className="h-full w-full rounded-card border border-border bg-surface p-4 text-left transition-colors duration-fast hover:bg-surface-2"
            >
              <span className="text-small uppercase tracking-wide text-muted">
                {demoCase.domain}
              </span>
              <span className="mt-1 block text-h3 font-semibold">{demoCase.title}</span>
              <span className="mt-2 block text-small text-muted">{demoCase.summary}</span>
              <span className="mt-3 block font-mono text-small text-muted">
                {findingCount(demoCase.data.deviations.length)} ·{" "}
                {durationLabel(demoCase.data.duration_s)} min
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
