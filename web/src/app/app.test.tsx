import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Report } from "../types/generated/report";

import { AppRoutes } from "./router";

const RUN_ID = "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ";
const HEX = "a".repeat(64);

const REPORT: Report = {
  schema_version: "1.0.0",
  run_id: RUN_ID,
  created_at: "2026-11-02T00:00:00Z",
  status: "done",
  degraded_stages: [],
  sop: {
    schema_version: "1.0.0",
    sop_id: "sop_01234567",
    title: "Cable check",
    source: { kind: "pasted", sha256: HEX },
    steps: [
      {
        id: "stp_01",
        idx: 1,
        text: "Unplug the power cable.",
        action: "Unplug the power cable.",
        tools: ["hand"],
        parts: ["power cable"],
        ordering: "strict",
        group_id: null,
        critical: false,
        visual_check: null,
      },
    ],
    vocabulary: { sam_concepts: ["hand"] },
    warnings: [],
  },
  video: { sha256: HEX, duration_s: 2, width: 320, height: 240 },
  lanes: {
    expected: [{ step_id: "stp_01", idx: 1 }],
    observed: [{ interval_id: "int_01", step_id: "stp_01", t_start: 0, t_end: 1 }],
  },
  deviations: [],
  summary: { flagged: 0, needs_review: 0, dropped: 0, by_type: { missed: 0, out_of_order: 0, wrong_tool: 0 } },
  manifest_ref: "manifest.json",
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

describe("app routes", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the shell with the product heading and primary navigation", () => {
    renderAt("/");

    expect(screen.getByRole("heading", { level: 1, name: "Process Watcher" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Check a procedure" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Demo" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to content" })).toBeInTheDocument();
  });

  it("shows the access gate on the landing route when no code is stored", () => {
    renderAt("/");

    expect(screen.getByRole("heading", { name: "Access code required" })).toBeInTheDocument();
  });

  it("shows the upload flow when a code is already stored", () => {
    window.sessionStorage.setItem("pw.access-code", "s3cret");

    renderAt("/");

    expect(screen.getByRole("heading", { name: "Check a procedure" })).toBeInTheDocument();
    expect(screen.getByLabelText("Procedure video")).toBeInTheDocument();
    expect(screen.getByLabelText("Written SOP")).toBeInTheDocument();
  });

  it("asks for the access code on a run route when none is stored", () => {
    renderAt(`/runs/${RUN_ID}`);

    expect(screen.getByRole("heading", { name: "Access code required" })).toBeInTheDocument();
  });

  it("loads the report for a finished run route", async () => {
    window.sessionStorage.setItem("pw.access-code", "s3cret");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).endsWith("/report")
          ? jsonResponse(REPORT)
          : jsonResponse({ run_id: RUN_ID, status: "done" }),
      ),
    );

    renderAt(`/runs/${RUN_ID}`);

    expect(await screen.findByRole("heading", { name: `Run ${RUN_ID}` })).toBeInTheDocument();
    expect(await screen.findByText("No deviations found.")).toBeInTheDocument();
  });

  it("renders the demo route", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          cases: [
            {
              case_id: "keyboard-compliant",
              title: "Keyboard clean: compliant run",
              description: "The operator follows the SOP.",
              source_run: RUN_ID,
              duration_s: 54.3333,
              deviation_count: 1,
            },
          ],
        }),
      ),
    );

    renderAt("/demo");

    expect(await screen.findByRole("heading", { name: "Demo cases" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /Keyboard clean: compliant run/i }),
    ).toBeInTheDocument();
  });

  it("renders a not-found state for an unknown route", () => {
    renderAt("/nope");

    expect(screen.getByRole("heading", { name: "Not found" })).toBeInTheDocument();
  });
});
