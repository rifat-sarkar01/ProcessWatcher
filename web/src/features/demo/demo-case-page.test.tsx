import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type ApiClient } from "../../api";
import { DemoCasePage } from "./demo-case-page";

function detailPayload(
  caseId: string,
  title: string,
  description: string,
  durationSeconds: number,
  deviations: { id: string; type: string; status: string; step_id: string; t_start: number; t_end: number }[],
) {
  return {
    case_id: caseId,
    title,
    description,
    source_run: "run_test",
    duration_s: durationSeconds,
    deviation_count: deviations.length,
    media: { analysis: "media/analysis.mp4" },
    report: {
      video: { duration_s: durationSeconds },
      lanes: {
        expected: [
          { step_id: "stp_01", idx: 1 },
          { step_id: "stp_02", idx: 2 },
        ],
        observed: [{ interval_id: "int_01", step_id: "stp_02", t_start: 1.8, t_end: 5.5 }],
      },
      deviations,
    },
  };
}

const COMPLIANT = detailPayload(
  "keyboard-compliant",
  "Keyboard clean: compliant run",
  "The operator follows the SOP; no finding is flagged, only one review-level note.",
  54.3333,
  [
    {
      id: "dev_001",
      type: "missed",
      status: "needs_review",
      step_id: "stp_06",
      t_start: 47.0222,
      t_end: 47.0222,
    },
  ],
);

const MISSED_TILT = detailPayload(
  "keyboard-missed-tilt",
  "Keyboard clean: tilt and tap omitted",
  "Step 1 is never performed; the aligner flags it as missed with 1.0 confidence.",
  28.4667,
  [
    { id: "dev_001", type: "missed", status: "flagged", step_id: "stp_01", t_start: 0, t_end: 1.8 },
    {
      id: "dev_002",
      type: "missed",
      status: "flagged",
      step_id: "stp_06",
      t_start: 21.2667,
      t_end: 28.4667,
    },
    {
      id: "dev_003",
      type: "missed",
      status: "flagged",
      step_id: "stp_07",
      t_start: 21.2667,
      t_end: 28.4667,
    },
  ],
);

function fakeClient(payload: unknown): ApiClient {
  return {
    setAccessCode: vi.fn(),
    get: vi.fn(async () => payload) as unknown as ApiClient["get"],
  };
}

function renderCase(caseId: string, client: ApiClient) {
  return render(
    <MemoryRouter initialEntries={[`/demo/${caseId}`]}>
      <Routes>
        <Route path="demo/:caseId" element={<DemoCasePage client={client} />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("DemoCasePage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.spyOn(window.HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  });

  it("opens the review surface for the selected case", async () => {
    renderCase("keyboard-compliant", fakeClient(COMPLIANT));

    expect(
      await screen.findByRole("heading", { name: "Keyboard clean: compliant run" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("timeline")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("keeps the offline badge and links back to the gallery", async () => {
    renderCase("keyboard-compliant", fakeClient(COMPLIANT));

    expect(await screen.findByText("Offline")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All demo cases" })).toHaveAttribute("href", "/demo");
  });

  it("lists the case deviations in the timeline", async () => {
    renderCase("keyboard-missed-tilt", fakeClient(MISSED_TILT));

    expect(await screen.findAllByTestId("deviation-marker")).toHaveLength(3);
  });

  it("appends the known-limitation note to the missed-tilt description", async () => {
    renderCase("keyboard-missed-tilt", fakeClient(MISSED_TILT));

    expect(
      await screen.findByText(/known short-step limitation/i),
    ).toBeInTheDocument();
  });

  it("shows a not-found state for an unknown case", async () => {
    const client: ApiClient = {
      setAccessCode: vi.fn(),
      get: vi.fn(async () => {
        throw new ApiError("not_found", 404);
      }) as unknown as ApiClient["get"],
    };

    renderCase("does-not-exist", client);

    expect(await screen.findByRole("heading", { name: "Case not found" })).toBeInTheDocument();
  });
});
