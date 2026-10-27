import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { readStoredAccessCode, storeAccessCode } from "../api";
import { DemoGallery } from "../features/demo/demo-gallery";
import { AccessGate } from "../ui/access-gate";
import { EmptyState } from "../ui/states";

/** Landing screen: gate first, upload lands here in T-5.7. */
export function HomePage() {
  const [accessCode, setAccessCode] = useState<string | null>(() => readStoredAccessCode());

  if (accessCode) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <EmptyState
          title="No runs yet"
          help="Upload a recorded procedure and its SOP to start a check. Upload arrives with T-5.7."
          action={
            <button
              type="button"
              className="min-h-11 rounded-control border border-border-strong px-4 text-control"
              onClick={() => {
                storeAccessCode(null);
                setAccessCode(null);
              }}
            >
              Change access code
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-xl">
      <AccessGate
        onSubmit={(code) => {
          storeAccessCode(code);
          setAccessCode(code);
        }}
      />
    </div>
  );
}

/** Run review screen: the player, lanes and deviation panel arrive in T-5.9–T-5.11. */
export function RunPage() {
  const { runId = "" } = useParams();

  return (
    <EmptyState
      title={`Run ${runId}`}
      help="The run view is not wired yet: it needs the runs API (T-5.2) and the review core (T-5.9)."
      action={
        <Link to="/" className="text-accent underline underline-offset-4">
          Back to start
        </Link>
      }
    />
  );
}

/** Demo gallery: frozen offline cases (T-5.12). */
export function DemoPage() {
  const navigate = useNavigate();
  return <DemoGallery onOpen={(caseId) => navigate(`/demo/${caseId}`)} />;
}

export function NotFoundPage() {
  return (
    <EmptyState
      title="Not found"
      help="That page does not exist."
      action={
        <Link to="/" className="text-accent underline underline-offset-4">
          Back to start
        </Link>
      }
    />
  );
}
