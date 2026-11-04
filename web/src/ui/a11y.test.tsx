import axe from "axe-core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "../app/router";

/**
 * axe over the four shipped routes (T-6.7).
 *
 * `color-contrast` is disabled here because jsdom has no layout engine and therefore
 * no computed colours; contrast is asserted against the design tokens themselves in
 * `tokens.test.ts`, which is stricter than a DOM guess.
 */
const ROUTES = [
  "/",
  "/runs/run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ",
  "/demo",
  "/demo/keyboard-compliant",
] as const;

const DEMO_SUMMARY = {
  case_id: "keyboard-compliant",
  title: "Keyboard clean: compliant run",
  description: "The operator follows the SOP.",
  source_run: "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ",
  duration_s: 54.3333,
  deviation_count: 1,
};

const DEMO_DETAIL = {
  ...DEMO_SUMMARY,
  media: { analysis: "media/analysis.mp4" },
  report: {
    video: { duration_s: 54.3333 },
    lanes: {
      expected: [{ step_id: "stp_01", idx: 1 }],
      observed: [{ interval_id: "int_01", step_id: "stp_01", t_start: 0, t_end: 5 }],
    },
    deviations: [],
  },
};

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

function mockDemoApi() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.endsWith("/demo/cases")) return jsonResponse({ cases: [DEMO_SUMMARY] });
    if (path.includes("/demo/cases/")) return jsonResponse(DEMO_DETAIL);
    return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
  });
}

async function audit(path: string) {
  window.sessionStorage.clear();
  const { container } = render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );

  if (path.startsWith("/demo")) {
    await screen.findByText("Keyboard clean: compliant run");
  }

  const results = await axe.run(container, {
    rules: {
      "color-contrast": { enabled: false },
    },
  });

  return results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
}

describe("accessibility", () => {
  beforeEach(() => {
    vi.spyOn(window.HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    // jsdom has no canvas; axe probes it and would log a "Not implemented" warning.
    vi.spyOn(window.HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    vi.stubGlobal("fetch", mockDemoApi());
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each(ROUTES)("route %s has no serious or critical axe violations", async (path) => {
    const violations = await audit(path);

    expect(violations.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([]);
  });

  it("detects a planted violation, proving the harness is real", async () => {
    const { container } = render(<img src="planted.png" />);

    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });

    expect(results.violations.map((violation) => violation.id)).toContain("image-alt");
  });
});
