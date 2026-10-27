import { Link, useParams } from "react-router-dom";

import { EmptyState } from "../../ui/states";
import { ReviewSurface } from "../review/player/review-surface";
import { DEMO_CASES } from "./cases";

/** `/demo/:caseId`: the review core loaded with frozen data. */
export function DemoCasePage() {
  const { caseId = "" } = useParams();
  const demoCase = DEMO_CASES.find((candidate) => candidate.id === caseId);

  if (!demoCase) {
    return (
      <EmptyState
        title="Case not found"
        help="That demo case is not part of the frozen set."
        action={
          <Link to="/demo" className="text-accent underline underline-offset-4">
            All demo cases
          </Link>
        }
      />
    );
  }

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="m-0 text-h2 font-semibold">{demoCase.title}</h2>
        <span className="rounded-chip border border-illustration px-2 py-0.5 text-small text-illustration">
          Offline
        </span>
      </header>

      <p className="m-0 text-small text-muted">
        {demoCase.domain} · {demoCase.summary}
      </p>

      <Link to="/demo" className="inline-block text-small text-accent underline underline-offset-4">
        All demo cases
      </Link>

      <ReviewSurface
        src={`/demo/cases/${demoCase.id}/media/analysis.mp4`}
        data={demoCase.data}
      />
    </section>
  );
}
